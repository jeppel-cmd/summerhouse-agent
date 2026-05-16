from __future__ import annotations

import argparse
import math
import os
import re
import sys
import time
import warnings
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

external_site_packages = Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python314" / "Lib" / "site-packages"
if external_site_packages.exists():
    sys.path.insert(0, str(external_site_packages))
project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / ".vendor_local"))

warnings.filterwarnings("ignore", message="Unable to find acceptable character detection dependency")

import requests


BASE_URL = "https://api.boliga.dk/api/v2/search/results"
LISTING_WEB_ROOT = "https://www.boliga.dk"
DEFAULT_PAGE_SIZE = 50


class BoligaBlockedError(RuntimeError):
    """Raised when Boliga returns a browser challenge instead of JSON."""


@dataclass
class ScrapeResult:
    listings: list[dict[str, Any]]
    total_count: int | None
    pages_fetched: int


def default_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "da-DK,da;q=0.9,en-US;q=0.8,en;q=0.7",
        "Origin": "https://www.boliga.dk",
        "Referer": "https://www.boliga.dk/boliger/fritidshuse",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    }
    cookie = os.getenv("BOLIGA_COOKIE")
    if cookie:
        headers["Cookie"] = cookie
    return headers


def fetch_page(page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict[str, Any]:
    params = {
        "searchTab": 1,
        "propertyType": 4,
        "page": page,
        "pagesize": page_size,
        "sort": "daysForSale-a",
    }
    response = requests.get(BASE_URL, params=params, headers=default_headers(), timeout=30)
    content_type = response.headers.get("content-type", "")
    text_start = response.text[:300].lower()

    if "text/html" in content_type or "enable javascript and cookies" in text_start:
        raise BoligaBlockedError(
            "Boliga returned a Cloudflare browser challenge instead of JSON. "
            "Try again later, or set BOLIGA_COOKIE to valid cookies from your browser session."
        )

    response.raise_for_status()
    return response.json()


def extract_items(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int | None]:
    for key in ("result", "results", "items", "estates"):
        value = payload.get(key)
        if isinstance(value, list):
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            total = (
                payload.get("totalCount")
                or payload.get("total")
                or payload.get("count")
                or meta.get("totalCount")
            )
            return value, int(total) if isinstance(total, int) else None
    raise ValueError(f"Could not find a listing array in API payload keys: {sorted(payload.keys())}")


def get_any(source: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in source and source[name] not in ("", None):
            return source[name]
    return None


def to_int(value: Any) -> int | None:
    if value in ("", None):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return round(value)
    try:
        return int(float(str(value).replace(".", "").replace(",", ".")))
    except ValueError:
        return None


def to_float(value: Any) -> float | None:
    if value in ("", None):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(",", "."))
    except ValueError:
        return None


def region_from_postal(postal_code: int | None) -> str | None:
    if postal_code is None:
        return None
    if 1000 <= postal_code <= 3999:
        return "Region Hovedstaden"
    if 4000 <= postal_code <= 4999:
        return "Region Sjælland"
    if 5000 <= postal_code <= 6999:
        return "Region Syddanmark"
    if 7000 <= postal_code <= 8999:
        return "Region Midtjylland"
    if 9000 <= postal_code <= 9999:
        return "Region Nordjylland"
    return None


def listing_url(raw: dict[str, Any], listing_id: str) -> str:
    raw_url = get_any(raw, "url", "path", "link")
    if raw_url:
        return raw_url if str(raw_url).startswith("http") else f"{LISTING_WEB_ROOT}{raw_url}"

    slug = get_any(raw, "slug", "addressSlug", "ouAddress")
    address_id = get_any(raw, "ouId")
    if slug:
        suffix_id = address_id or listing_id
        return f"{LISTING_WEB_ROOT}/adresse/{slug}-{suffix_id}"
    return f"{LISTING_WEB_ROOT}/adresse/{listing_id}"


def normalize_listing(raw: dict[str, Any]) -> dict[str, Any]:
    listing_id = str(get_any(raw, "id", "estateId", "propertyId", "guid"))
    if listing_id in ("None", ""):
        raise ValueError(f"Listing has no obvious ID: {raw}")

    postal_code = to_int(get_any(raw, "zipCode", "zipcode", "postalCode", "postal_code"))
    price = to_int(get_any(raw, "price", "cashPrice", "askingPrice"))
    size = to_float(get_any(raw, "size", "livingArea", "area", "sqm"))
    sqm_price = to_int(get_any(raw, "squaremeterPrice", "sqmPrice", "pricePerSqm", "price_per_m2"))

    if sqm_price is None and price and size:
        sqm_price = round(price / size)

    region = get_any(raw, "region", "regionName") or region_from_postal(postal_code)
    address = get_any(raw, "address", "street", "roadName", "displayAddress")
    city = get_any(raw, "city", "cityName", "postalName")

    return {
        "listing_id": listing_id,
        "address": address,
        "city": city,
        "postal_code": postal_code,
        "region": region,
        "asking_price": price,
        "price_per_m2": sqm_price,
        "size_m2": size,
        "rooms": to_float(get_any(raw, "rooms", "numberOfRooms")),
        "year_built": to_int(get_any(raw, "buildYear", "yearBuilt", "constructionYear")),
        "energy_rating": (str(get_any(raw, "energyClass", "energyRating", "energyLabel")).upper()
                          if get_any(raw, "energyClass", "energyRating", "energyLabel") else None),
        "days_on_market": to_int(get_any(raw, "daysForSale", "daysOnMarket", "dom")),
        "listing_url": listing_url(raw, listing_id),
        "latitude": to_float(get_any(raw, "lat", "latitude")),
        "longitude": to_float(get_any(raw, "lon", "lng", "longitude")),
        "raw": raw,
    }


def fetch_all(max_pages: int | None = None, delay_seconds: float = 0.4) -> ScrapeResult:
    first_payload = fetch_page(1)
    first_items, total_count = extract_items(first_payload)
    listings = [normalize_listing(item) for item in first_items]

    if total_count:
        total_pages = math.ceil(total_count / DEFAULT_PAGE_SIZE)
    else:
        total_pages = 1

    if max_pages:
        total_pages = min(total_pages, max_pages)

    for page in range(2, total_pages + 1):
        time.sleep(delay_seconds)
        payload = fetch_page(page)
        items, _ = extract_items(payload)
        if not items:
            break
        listings.extend(normalize_listing(item) for item in items)

    return ScrapeResult(listings=listings, total_count=total_count, pages_fetched=total_pages)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch Boliga fritidshus listings without storing them.")
    parser.add_argument("--max-pages", type=int, default=1, help="Limit pages while testing.")
    args = parser.parse_args()

    try:
        result = fetch_all(max_pages=args.max_pages)
    except BoligaBlockedError as exc:
        print(f"BLOCKED: {exc}")
        raise SystemExit(2)

    print(f"Fetched {len(result.listings)} listings from {result.pages_fetched} page(s).")
    if result.total_count is not None:
        print(f"API total_count: {result.total_count}")
    for listing in result.listings[:3]:
        print(
            f"{listing['listing_id']}: {listing.get('address')}, "
            f"{listing.get('postal_code')} {listing.get('city')} - "
            f"{listing.get('asking_price')} DKK"
        )


if __name__ == "__main__":
    main()
