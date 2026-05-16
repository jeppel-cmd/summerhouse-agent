from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
from datetime import datetime
from typing import Any

SOURCE_NAME = "kamp_storm_surge_openmeteo_elevation_dingeo_historical_v2"
KAMP_STORM_SURGE_URL = "https://services9.arcgis.com/qH1Ysxh3VVYXbkQU/arcgis/rest/services/VandstandStormflodKyst_latest/FeatureServer/0/query"
OPEN_METEO_ELEVATION_URL = "https://api.open-meteo.com/v1/elevation"
OSD_FLOODED_AREAS_RECORD_URL = "https://geodata-info.dk/srv/api/records/a71f9737-ede1-448a-bda2-5120f65d8ded"


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _query_kamp_nearby(lat: float, lon: float, delta_deg: float = 0.18) -> list[dict[str, Any]]:
    params = {
        "where": "1=1",
        "geometry": f"{lon - delta_deg},{lat - delta_deg},{lon + delta_deg},{lat + delta_deg}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "kystnavn,kystkode,Stormfl20Aarsh,Stormfl100Aarsh,StormflNuvaerende100Aarsh,Vandst5Aarsh,version",
        "returnGeometry": "true",
        "outSR": "4326",
        "f": "json",
        "resultRecordCount": "2000",
    }
    url = KAMP_STORM_SURGE_URL + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "summerhouse-agent/1.0"})
    payload = json.load(urllib.request.urlopen(req, timeout=30))
    return payload.get("features", [])


def nearest_kamp_coast_point(lat: float, lon: float) -> dict[str, Any] | None:
    features = _query_kamp_nearby(lat, lon)
    candidates = []
    for feature in features:
        geom = feature.get("geometry") or {}
        attrs = feature.get("attributes") or {}
        if geom.get("x") is None or geom.get("y") is None:
            continue
        distance_km = haversine_km(lat, lon, float(geom["y"]), float(geom["x"]))
        candidates.append({"distance_km": distance_km, "attributes": attrs})
    if not candidates:
        return None
    nearest = min(candidates, key=lambda item: item["distance_km"])
    attrs = nearest["attributes"]
    return {
        "coast_name": str(attrs.get("kystnavn") or "").strip() or None,
        "coast_code": attrs.get("kystkode"),
        "distance_km": round(nearest["distance_km"], 1),
        "storm_surge_20y_cm": attrs.get("Stormfl20Aarsh"),
        "storm_surge_100y_cm": attrs.get("Stormfl100Aarsh") or attrs.get("StormflNuvaerende100Aarsh"),
        "source_version": attrs.get("version"),
    }


def _open_url_json(url: str, timeout: int = 30) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "summerhouse-agent/1.0"})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def elevation_m(lat: float, lon: float) -> float | None:
    params = urllib.parse.urlencode({"latitude": lat, "longitude": lon})
    payload = _open_url_json(f"{OPEN_METEO_ELEVATION_URL}?{params}", timeout=20)
    values = payload.get("elevation")
    if not values:
        return None
    return round(float(values[0]), 1)


def dingeo_address_url(listing: dict[str, Any]) -> str | None:
    address = str(listing.get("address") or "").strip()
    city = str(listing.get("city") or "").strip()
    postal = listing.get("postal_code")
    if not address or not city or postal in ("", None):
        return None

    def slug(value: str) -> str:
        value = value.lower().strip()
        value = re.sub(r"\s+", "-", value)
        value = re.sub(r"[^0-9a-zæøåäöüéèáàíìóòúùß.-]+", "", value, flags=re.IGNORECASE)
        return urllib.parse.quote(value, safe="-")

    return f"https://www.dingeo.dk/adresse/{slug(f'{postal} {city}')}/{slug(address)}/"


def historical_flooding_hint(listing: dict[str, Any]) -> dict[str, Any]:
    """Return a conservative historical-flooding hint.

    DinGeo exposes historical/known flooding context on address pages, but the site is
    Cloudflare-protected from this server. The official INSPIRE OSD metadata record for
    observed flooded areas is kept as a source pointer; until its downloadable geometry
    is available locally, we flag this as a manual check instead of inventing a result.
    """
    return {
        "status": "manual_check_required",
        "observed_flooding": None,
        "source": "DinGeo + OSD (Observed/Flooded areas) metadata",
        "dingeo_url": dingeo_address_url(listing),
        "osd_metadata_url": OSD_FLOODED_AREAS_RECORD_URL,
        "note": "Historiske oversvømmelser er ikke automatisk bekræftet endnu; tjek DinGeo-linket for adressen.",
    }


def elevation_warning_level(elevation: float | None, coast_distance_km: float | None) -> str:
    if elevation is None:
        return "unknown"
    if elevation <= 2.0:
        return "high"
    if elevation <= 4.0:
        return "medium" if coast_distance_km is None or coast_distance_km <= 7.5 else "watch"
    if elevation <= 6.0:
        return "watch"
    return "low"


def combine_warning_levels(*levels: str) -> str:
    order = {"unknown": 0, "low": 1, "watch": 2, "medium": 3, "high": 4}
    return max((level for level in levels if level), key=lambda level: order.get(level, 0), default="unknown")


def assess_listing(listing: dict[str, Any]) -> dict[str, Any]:
    lat = listing.get("latitude")
    lon = listing.get("longitude")
    now = datetime.now().isoformat(timespec="seconds")
    if lat in ("", None) or lon in ("", None):
        return {
            "listing_id": listing["listing_id"],
            "warning_level": "unknown",
            "warning_text": "Oversvømmelsesrisiko kunne ikke vurderes, fordi koordinater mangler.",
            "source": SOURCE_NAME,
            "trigger_json": {"historical_flooding": historical_flooding_hint(listing)},
            "last_checked_at": now,
        }

    lat_f = float(lat)
    lon_f = float(lon)
    nearest = None
    elevation = None
    errors: list[str] = []
    try:
        nearest = nearest_kamp_coast_point(lat_f, lon_f)
    except Exception as exc:
        errors.append(f"KAMP stormflodsopslag fejlede: {exc}")
    try:
        elevation = elevation_m(lat_f, lon_f)
    except Exception as exc:
        errors.append(f"Højdeopslag fejlede: {exc}")

    if nearest is None and elevation is None:
        return {
            "listing_id": listing["listing_id"],
            "warning_level": "unknown",
            "warning_text": "Oversvømmelsesrisiko kunne ikke vurderes automatisk. " + " ".join(errors),
            "source": SOURCE_NAME,
            "trigger_json": {"errors": errors, "historical_flooding": historical_flooding_hint(listing)},
            "last_checked_at": now,
        }

    distance = nearest.get("distance_km") if nearest else None
    surge_100 = nearest.get("storm_surge_100y_cm") if nearest else None
    coast_level = "unknown"
    if distance is not None:
        coast_level = "low"
        if distance <= 1.0:
            coast_level = "high"
        elif distance <= 3.0:
            coast_level = "medium"
        elif distance <= 7.5:
            coast_level = "watch"

    elev_level = elevation_warning_level(elevation, distance)
    level = combine_warning_levels(coast_level, elev_level)
    historical = historical_flooding_hint(listing)

    parts = []
    if elevation is not None:
        parts.append(f"Terrænhøjde er ca. {elevation} m over havet")
        if elevation <= 2:
            parts.append("meget lavtliggende grund")
        elif elevation <= 4:
            parts.append("lavtliggende grund")
        elif elevation <= 6:
            parts.append("relativt lavt terræn")
    if nearest:
        parts.append(
            f"nærmeste officielle KAMP-stormflodsreference er {distance} km væk"
            + (f" ved {nearest['coast_name']}" if nearest.get("coast_name") else "")
            + (f"; 100-års stormflod ca. {surge_100} cm" if surge_100 is not None else "")
        )
    parts.append("historiske oversvømmelser kræver foreløbig manuel DinGeo-tjek via linket i detaljevisningen")
    if errors:
        parts.append("Automatisk opslag havde fejl: " + " ".join(errors))

    text = ". ".join(parts) + ". Dette er en screeningsindikator, ikke en matrikelpræcis oversvømmelsesberegning."
    trigger = {
        "elevation_m": elevation,
        "elevation_source": "Open-Meteo elevation API (DEM-derived)",
        "low_lying_level": elev_level,
        "coast_reference": nearest,
        "coast_level": coast_level,
        "historical_flooding": historical,
        "errors": errors,
    }
    return {
        "listing_id": listing["listing_id"],
        "warning_level": level,
        "warning_text": text,
        "source": SOURCE_NAME,
        "trigger_json": trigger,
        "last_checked_at": now,
    }


def placeholder_warning(listing: dict[str, Any]) -> dict[str, Any]:
    return {
        "listing_id": listing["listing_id"],
        "warning_level": "unknown",
        "warning_text": "Geo-risiko er ikke tjekket endnu. Kør flood-risk enrichment for terrænhøjde, KAMP-stormflodsreference og DinGeo-link til historiske oversvømmelser.",
        "source": "pending_geo_risk_enrichment",
        "trigger_json": {"historical_flooding": historical_flooding_hint(listing)},
        "last_checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def _upsert_warning(conn, warning: dict[str, Any]) -> dict[str, Any]:
    conn.execute(
        """
        INSERT INTO flood_risk (
            listing_id, warning_level, warning_text, source, trigger_json, last_checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(listing_id) DO UPDATE SET
            warning_level = excluded.warning_level,
            warning_text = excluded.warning_text,
            source = excluded.source,
            trigger_json = excluded.trigger_json,
            last_checked_at = excluded.last_checked_at
        """,
        (
            warning["listing_id"],
            warning["warning_level"],
            warning["warning_text"],
            warning["source"],
            json.dumps(warning.get("trigger_json") or {}, ensure_ascii=False),
            warning["last_checked_at"],
        ),
    )
    return warning


def upsert_placeholder(conn, listing: dict[str, Any]) -> dict[str, Any]:
    return _upsert_warning(conn, placeholder_warning(listing))


def upsert_assessment(conn, listing: dict[str, Any]) -> dict[str, Any]:
    return _upsert_warning(conn, assess_listing(listing))
