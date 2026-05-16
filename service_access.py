from __future__ import annotations

import json
import math
import time
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

SOURCE_NAME = "openstreetmap_overpass_supermarket_v1"
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def supermarket_query(lat: float, lon: float, radius_m: int = 15000) -> str:
    return f"""
[out:json][timeout:25];
(
  node["shop"~"^(supermarket|convenience)$"](around:{radius_m},{lat},{lon});
  way["shop"~"^(supermarket|convenience)$"](around:{radius_m},{lat},{lon});
  relation["shop"~"^(supermarket|convenience)$"](around:{radius_m},{lat},{lon});
);
out center tags;
""".strip()


def fetch_nearest_supermarket(lat: float, lon: float, radius_m: int = 15000) -> dict[str, Any]:
    data = urllib.parse.urlencode({"data": supermarket_query(lat, lon, radius_m)}).encode()
    last_error: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            req = urllib.request.Request(endpoint, data=data, headers={"User-Agent": "summerhouse-agent/1.0"})
            payload = json.load(urllib.request.urlopen(req, timeout=35))
            candidates = []
            for element in payload.get("elements", []):
                el_lat = element.get("lat") or (element.get("center") or {}).get("lat")
                el_lon = element.get("lon") or (element.get("center") or {}).get("lon")
                if el_lat is None or el_lon is None:
                    continue
                distance = round(haversine_m(lat, lon, float(el_lat), float(el_lon)))
                tags = element.get("tags") or {}
                candidates.append({
                    "name": tags.get("name") or tags.get("brand") or "Supermarket/service",
                    "distance_m": distance,
                    "lat": float(el_lat),
                    "lon": float(el_lon),
                    "shop": tags.get("shop"),
                    "brand": tags.get("brand"),
                })
            if not candidates:
                return {
                    "status": "not_found",
                    "nearest_name": None,
                    "nearest_distance_m": None,
                    "estimated_car_minutes": None,
                    "source": SOURCE_NAME,
                    "checked_at": datetime.now().isoformat(timespec="seconds"),
                }
            nearest = min(candidates, key=lambda item: item["distance_m"])
            # Rural driving proxy: road distance ~= 1.35x straight-line, average 55 km/h + 3 min overhead.
            car_minutes = round((nearest["distance_m"] * 1.35 / 1000) / 55 * 60 + 3)
            return {
                "status": "ok",
                "nearest_name": nearest["name"],
                "nearest_distance_m": nearest["distance_m"],
                "estimated_car_minutes": car_minutes,
                "nearest_lat": nearest["lat"],
                "nearest_lon": nearest["lon"],
                "source": SOURCE_NAME,
                "checked_at": datetime.now().isoformat(timespec="seconds"),
            }
        except Exception as exc:  # network/API fallback
            last_error = exc
            time.sleep(1)
    return {
        "status": "error",
        "error": str(last_error) if last_error else "unknown error",
        "nearest_name": None,
        "nearest_distance_m": None,
        "estimated_car_minutes": None,
        "source": SOURCE_NAME,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def enrich_listing_raw(raw: dict[str, Any], lat: float, lon: float) -> dict[str, Any]:
    enriched = dict(raw)
    enriched["service_access"] = fetch_nearest_supermarket(lat, lon)
    return enriched
