from __future__ import annotations

import json
import math
import re
import statistics
from datetime import date, datetime, timedelta, timezone
from typing import Any

import area_research
import flood_risk
import preferences as preference_store


SCORE_VERSION = "deterministic-v2"
CPH_CENTRAL_LAT = 55.6728
CPH_CENTRAL_LON = 12.5655


def clamp(value: float, low: float = 0, high: float = 100) -> float:
    return max(low, min(high, value))


def row_to_dict(row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def parse_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def raw_for(listing: dict[str, Any]) -> dict[str, Any]:
    raw = parse_json(listing.get("raw_json"), {})
    return raw if isinstance(raw, dict) else {}


def text_blob(listing: dict[str, Any], raw: dict[str, Any]) -> str:
    parts = [
        listing.get("address"),
        listing.get("city"),
        raw.get("ouAddress"),
        raw.get("cleanStreet"),
        raw.get("street"),
        raw.get("description"),
        raw.get("descriptionBody"),
        raw.get("remarks"),
    ]
    return " ".join(str(part).lower() for part in parts if part)


def postal_code(listing: dict[str, Any]) -> int | None:
    value = listing.get("postal_code")
    return int(value) if value not in ("", None) else None


def is_sjaelland_area(listing: dict[str, Any]) -> bool:
    postal = postal_code(listing)
    if postal is None:
        return False
    return 1000 <= postal <= 4999


def ferry_warning(listing: dict[str, Any]) -> bool:
    postal = postal_code(listing)
    if postal is None:
        return False
    return 3700 <= postal <= 3799


def straight_line_km(listing: dict[str, Any]) -> float | None:
    lat = listing.get("latitude")
    lon = listing.get("longitude")
    if lat in ("", None) or lon in ("", None):
        return None
    try:
        lat1 = math.radians(CPH_CENTRAL_LAT)
        lon1 = math.radians(CPH_CENTRAL_LON)
        lat2 = math.radians(float(lat))
        lon2 = math.radians(float(lon))
    except (TypeError, ValueError):
        return None
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 6371 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def travel_estimates(listing: dict[str, Any]) -> dict[str, int | None]:
    distance = straight_line_km(listing)
    if distance is None:
        return {"distance_km": None, "car_minutes": None, "public_transport_minutes": None}

    postal = postal_code(listing) or 0
    route_factor = 1.28
    car_minutes = (distance * route_factor / 70) * 60 + 12
    public_minutes = (distance * 1.42 / 48) * 60 + 28

    if 4500 <= postal <= 4599:
        public_minutes += 12
    if 4700 <= postal <= 4999:
        public_minutes += 30
        car_minutes += 10
    if ferry_warning(listing):
        public_minutes += 75
        car_minutes += 55

    return {
        "distance_km": round(distance),
        "car_minutes": round(car_minutes),
        "public_transport_minutes": round(public_minutes),
    }


def location_score(listing: dict[str, Any], prefs: dict[str, Any], reasons: list[str]) -> float:
    postal = postal_code(listing)
    if postal is None:
        reasons.append("Postnummer mangler, så beliggenheden er vurderet forsigtigt.")
        return 45

    if ferry_warning(listing):
        reasons.append("Færge-afhængig beliggenhed (fx Bornholm) passer ikke til kriterierne.")
        return 5
    if 4000 <= postal <= 4999:
        reasons.append("Ligger i Region Sjælland og matcher den ønskede geografi.")
        return 95
    if 1000 <= postal <= 3699 and prefs.get("regions", {}).get("include_hovedstaden", True):
        reasons.append("Ligger i Hovedstaden eller tæt på København.")
        return 80
    if is_sjaelland_area(listing):
        return 70
    reasons.append("Ligger uden for det primære Sjælland-fokus.")
    return 30


def travel_score(listing: dict[str, Any], reasons: list[str]) -> tuple[float, dict[str, int | None]]:
    estimates = travel_estimates(listing)
    public_minutes = estimates["public_transport_minutes"]
    car_minutes = estimates["car_minutes"]
    postal = postal_code(listing)
    if postal is None or public_minutes is None or car_minutes is None:
        return 45, estimates
    if ferry_warning(listing):
        return 5, estimates

    if public_minutes <= 90 and car_minutes <= 80:
        reasons.append("Rejseproxy ser stærk ud fra København H.")
        return 95, estimates
    if public_minutes <= 120 and car_minutes <= 100:
        return 84, estimates
    if public_minutes <= 135 and car_minutes <= 115:
        reasons.append("Rejseproxy er lidt over 2 timer med offentlig transport, så den markeres som advarsel frem for at blive sorteret fra.")
        return 66, estimates
    if public_minutes <= 150 and car_minutes <= 125:
        reasons.append("Rejseproxy er over 2 timer med offentlig transport og bør tjekkes manuelt.")
        return 48, estimates
    if public_minutes <= 170:
        reasons.append("Rejseproxy er sandsynligvis over ønsket om maks. to timer med offentlig transport.")
        return 35, estimates
    reasons.append("Rejseproxy ser for lang ud fra København H.")
    return 12, estimates


def nature_water_score(listing: dict[str, Any], raw: dict[str, Any], reasons: list[str]) -> float:
    blob = text_blob(listing, raw)
    water_terms = ("strand", "hav", "kyst", "fjord", "bugt", "baek", "bæk", "soe", "sø", "havn")
    nature_terms = ("skov", "natur", "eng", "mark", "lund", "lyng", "hegn", "klit")
    score = 45
    if any(term in blob for term in water_terms):
        score += 30
        reasons.append("Adresse eller bynavn peger på nærhed til vand.")
    if any(term in blob for term in nature_terms):
        score += 18
        reasons.append("Adresse eller bynavn peger på natur eller rolige omgivelser.")
    postal = postal_code(listing)
    if postal and 4500 <= postal <= 4599:
        score += 8
    return clamp(score)


def privacy_score(listing: dict[str, Any], raw: dict[str, Any], reasons: list[str]) -> float:
    lot_size = raw.get("lotSize")
    try:
        lot_size = float(lot_size)
    except (TypeError, ValueError):
        lot_size = None

    score = 45
    if lot_size:
        if lot_size >= 1500:
            score = 88
            reasons.append("Stor grund giver potentiale for privatliv og familiebrug.")
        elif lot_size >= 900:
            score = 72
        elif lot_size >= 500:
            score = 58
        else:
            score = 38

    city = str(listing.get("city") or "").lower()
    if any(term in city for term in ("kobenhavn", "koebenhavn", "roskilde", "naestved", "næstved")):
        score -= 10
    return clamp(score)


def rental_score(listing: dict[str, Any], raw: dict[str, Any], nature_score: float) -> float:
    rooms = listing.get("rooms") or 0
    size = listing.get("size_m2") or 0
    score = 35
    if nature_score >= 70:
        score += 18
    if rooms >= 3:
        score += 15
    if size >= 65:
        score += 12
    if is_sjaelland_area(listing):
        score += 10
    if str(listing.get("energy_rating") or "").upper() in {"A", "B", "C"}:
        score += 8
    return clamp(score)


def medians_for(listings: list[dict[str, Any]]) -> dict[str, float]:
    groups: dict[str, list[float]] = {}
    for listing in listings:
        ppm = listing.get("price_per_m2")
        postal = postal_code(listing)
        if not ppm or not postal:
            continue
        groups.setdefault(f"prefix:{str(postal)[:2]}", []).append(float(ppm))
        region_key = listing.get("region") or "unknown"
        groups.setdefault(f"region:{region_key}", []).append(float(ppm))
    return {
        key: statistics.median(values)
        for key, values in groups.items()
        if len(values) >= 5
    }


def value_score(listing: dict[str, Any], medians: dict[str, float], reasons: list[str]) -> float:
    ppm = listing.get("price_per_m2")
    postal = postal_code(listing)
    if not ppm or not postal:
        return 45

    benchmark = medians.get(f"prefix:{str(postal)[:2]}") or medians.get(f"region:{listing.get('region')}")
    if not benchmark:
        return 55

    ratio = float(ppm) / benchmark
    if ratio <= 0.75:
        reasons.append("Pris pr. m² ligger tydeligt under det lokale niveau.")
        return 92
    if ratio <= 0.9:
        reasons.append("Pris pr. m² ligger under det lokale niveau.")
        return 78
    if ratio <= 1.05:
        return 62
    if ratio <= 1.25:
        return 44
    reasons.append("Pris pr. m² ligger højt i forhold til det lokale niveau.")
    return 25


def renovation_signal(listing: dict[str, Any], raw: dict[str, Any]) -> bool:
    blob = text_blob(listing, raw)
    terms = (
        "renovering",
        "renoveringsprojekt",
        "modernisering",
        "istandsættelse",
        "istandsaettelse",
        "håndværkertilbud",
        "haandvaerkertilbud",
        "kærlig hånd",
        "kaerlig haand",
        "trænger",
        "traenger",
    )
    return any(term in blob for term in terms)


def price_fit_score(listing: dict[str, Any], prefs: dict[str, Any], raw: dict[str, Any], reasons: list[str]) -> float:
    price = listing.get("asking_price")
    if price in ("", None):
        reasons.append("Pris mangler, så budgetmatch vurderes forsigtigt.")
        return 45
    price = float(price)
    budget = prefs.get("budget", {})
    ideal_min = float(budget.get("ideal_min") or 2_000_000)
    ideal_max = float(budget.get("ideal_max") or 2_500_000)
    move_in_ready_max = float(budget.get("move_in_ready_max") or 3_000_000)
    renovation_max = float(budget.get("renovation_max") or 2_000_000)
    is_renovation = renovation_signal(listing, raw)

    if ideal_min <= price <= ideal_max:
        reasons.append("Pris ligger i idealbudgettet på ca. 2-2,5 mio. kr.")
        return 95
    if price < ideal_min:
        if is_renovation:
            reasons.append("Pris ligger under idealbudgettet; renoveringsstanden skal tjekkes, men den lave pris er et plus hvis huset ellers passer.")
            return 95
        reasons.append("Pris ligger under idealbudgettet og tæller positivt, hvis huset ellers passer.")
        return 98
    if is_renovation and price <= renovation_max:
        reasons.append("Renoveringsprojekt under ca. 2 mio. kr., som kan være interessant hvis standen matcher prisen.")
        return 90
    if price <= move_in_ready_max:
        reasons.append("Pris er under maks. 3 mio. kr., men over idealbudgettet.")
        return 68
    if price <= move_in_ready_max * 1.15:
        reasons.append("Pris er over 3 mio. kr.; kun interessant som prisfaldskandidat eller hvis alt andet er meget stærkt.")
        return 34
    reasons.append("Pris er klart over 3 mio. kr. og bør kun overvåges for større prisfald.")
    return 15


def bedroom_score(listing: dict[str, Any], prefs: dict[str, Any], raw: dict[str, Any], reasons: list[str]) -> float:
    required_bedrooms = int((prefs.get("house", {}) or {}).get("bedrooms_min") or 3)
    explicit_bedrooms = raw.get("bedrooms") or raw.get("numberOfBedrooms") or raw.get("bedroomCount")
    if explicit_bedrooms not in ("", None):
        try:
            bedrooms = float(explicit_bedrooms)
        except (TypeError, ValueError):
            bedrooms = None
        if bedrooms is not None:
            if bedrooms >= required_bedrooms:
                return 95
            reasons.append(f"Kun {bedrooms:g} registrerede soveværelser mod ønsket om {required_bedrooms}.")
            return 25

    rooms = listing.get("rooms")
    if rooms in ("", None):
        reasons.append("Antal værelser/soveværelser mangler, så familieegnethed vurderes forsigtigt.")
        return 45
    try:
        rooms = float(rooms)
    except (TypeError, ValueError):
        return 45

    # Boliga exposes rooms, not always bedrooms. For 3 bedrooms we conservatively prefer 4+ rooms
    # (living room + 3 bedrooms) and warn on 3 rooms.
    if rooms >= required_bedrooms + 1:
        return 88
    if rooms >= required_bedrooms:
        reasons.append("Boliga viser 3 værelser, men ønsket er 3 soveværelser; planløsningen skal tjekkes manuelt.")
        return 55
    reasons.append("For få værelser i forhold til ønsket om 3 soveværelser.")
    return 20


def service_access_score(listing: dict[str, Any], raw: dict[str, Any], reasons: list[str]) -> float:
    service = raw.get("service_access") if isinstance(raw.get("service_access"), dict) else {}
    minutes = service.get("estimated_car_minutes")
    name = service.get("nearest_name")
    if minutes not in ("", None):
        try:
            minutes = float(minutes)
        except (TypeError, ValueError):
            minutes = None
    if minutes is not None:
        if minutes <= 10:
            reasons.append(f"Nærmeste supermarked/service ser ud til at være ca. {minutes:g} min i bil væk" + (f" ({name})." if name else "."))
            return 92
        if minutes <= 20:
            return 75
        reasons.append(f"Serviceadgang kan være svag: nærmeste supermarked/service estimeres til ca. {minutes:g} min i bil.")
        return 35

    if ferry_warning(listing):
        return 10
    return 60


def momentum_score(listing: dict[str, Any], raw: dict[str, Any], reasons: list[str]) -> tuple[float, bool]:
    days = listing.get("days_on_market") or 0
    price_drop_total = raw.get("priceChangeCashTotal") or 0
    price_drop_percent = raw.get("priceChangePercentTotal") or 0
    has_drop = bool(listing.get("last_price_drop_date")) or float(price_drop_total or 0) < 0 or float(price_drop_percent or 0) < 0

    score = 45
    motivated = False
    if has_drop:
        score += 28
        motivated = True
        reasons.append("Prisfald tyder på en mere motiveret sælger.")
    if days >= 120:
        score += 12
        motivated = True
        reasons.append("Lang liggetid kan give forhandlingsrum.")
    elif days <= 14:
        score += 10
        reasons.append("Ny annonce, som er værd at se før den bliver opdaget bredt.")
    return clamp(score), motivated


def feedback_adjustment(listing_id: str, feedback_map: dict[str, set[str]], reasons: list[str]) -> float:
    types = feedback_map.get(listing_id, set())
    if "dislike" in types or "hide" in types:
        reasons.append("Nedprioriteret på baggrund af din feedback.")
        return -100
    adjustment = 0
    if "favorite" in types or "love" in types:
        adjustment += 8
    if "like" in types or "watch" in types:
        adjustment += 5
    if "too_expensive" in types:
        adjustment -= 8
    if "bad_location" in types:
        adjustment -= 12
    if "interesting_but_risky" in types:
        adjustment -= 3
    return adjustment


def score_listing(
    listing: dict[str, Any],
    prefs: dict[str, Any],
    medians: dict[str, float],
    feedback_map: dict[str, set[str]],
) -> dict[str, Any]:
    reasons: list[str] = []
    raw = raw_for(listing)

    loc = location_score(listing, prefs, reasons)
    travel, travel_meta = travel_score(listing, reasons)
    nature = nature_water_score(listing, raw, reasons)
    privacy = privacy_score(listing, raw, reasons)
    rental = rental_score(listing, raw, nature)
    value = value_score(listing, medians, reasons)
    price_fit = price_fit_score(listing, prefs, raw, reasons)
    bedrooms = bedroom_score(listing, prefs, raw, reasons)
    services = service_access_score(listing, raw, reasons)
    momentum, motivated = momentum_score(listing, raw, reasons)
    matched_area = area_research.match_area_profile(listing)
    area_score, area_adjust = area_research.area_adjustment(matched_area)
    if matched_area:
        if area_adjust > 0:
            reasons.append(f"Områdebonus: {matched_area['name']} passer godt til ønsket om personlig, brofast sommerhusjagt.")
        elif area_adjust < 0:
            reasons.append(f"Område-advarsel: {matched_area['name']} virker mindre oplagt til jeres ønsker.")

    fit = (
        loc * 0.16
        + travel * 0.15
        + nature * 0.13
        + privacy * 0.08
        + rental * 0.05
        + value * 0.17
        + price_fit * 0.16
        + bedrooms * 0.06
        + services * 0.02
        + momentum * 0.02
    )
    fit += area_adjust
    if ferry_warning(listing):
        fit = min(fit, 42)
    fit += feedback_adjustment(str(listing["listing_id"]), feedback_map, reasons)
    fit = clamp(round(fit, 1))

    hidden_gem = fit >= 72 and value >= 75 and (raw.get("views") or 0) <= 60
    if hidden_gem:
        reasons.append("Skjult perle: stærkt match, god relativ pris og lav synlig aktivitet.")

    if ferry_warning(listing):
        reasons.append("Færge-advarsel: tjek adgangsruten før den overvejes.")

    components = {
        "location_score": round(loc, 1),
        "travel_score": round(travel, 1),
        "nature_water_score": round(nature, 1),
        "privacy_score": round(privacy, 1),
        "rental_score": round(rental, 1),
        "value_score": round(value, 1),
        "price_fit_score": round(price_fit, 1),
        "bedroom_score": round(bedrooms, 1),
        "service_access_score": round(services, 1),
        "momentum_score": round(momentum, 1),
        "area_research_score": round(area_score, 1),
        "area_research_adjustment": round(area_adjust, 1),
        "area_research_id": matched_area.get("id") if matched_area else None,
        "area_research_name": matched_area.get("name") if matched_area else None,
        "distance_km_from_cph": travel_meta["distance_km"],
        "estimated_car_minutes": travel_meta["car_minutes"],
        "estimated_public_transport_minutes": travel_meta["public_transport_minutes"],
    }
    return {
        "listing_id": str(listing["listing_id"]),
        "scored_at": datetime.now().isoformat(timespec="seconds"),
        "score_version": SCORE_VERSION,
        "fit_score": fit,
        "hidden_gem": hidden_gem,
        "motivated_seller": motivated,
        "reasons": reasons[:8],
        "components": components,
    }


def load_active_listings(conn) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM listings WHERE status = 'active'").fetchall()
    return [row_to_dict(row) for row in rows]


def load_feedback_map(conn) -> dict[str, set[str]]:
    rows = conn.execute("SELECT listing_id, feedback_type FROM feedback").fetchall()
    feedback: dict[str, set[str]] = {}
    for row in rows:
        feedback.setdefault(str(row["listing_id"]), set()).add(row["feedback_type"])
    return feedback


def upsert_score(conn, score: dict[str, Any]) -> None:
    components = score["components"]
    conn.execute(
        """
        INSERT INTO listing_scores (
            listing_id, scored_at, score_version, fit_score,
            location_score, travel_score, nature_water_score, privacy_score,
            rental_score, value_score, momentum_score,
            hidden_gem, motivated_seller, reasons_json, components_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(listing_id) DO UPDATE SET
            scored_at = excluded.scored_at,
            score_version = excluded.score_version,
            fit_score = excluded.fit_score,
            location_score = excluded.location_score,
            travel_score = excluded.travel_score,
            nature_water_score = excluded.nature_water_score,
            privacy_score = excluded.privacy_score,
            rental_score = excluded.rental_score,
            value_score = excluded.value_score,
            momentum_score = excluded.momentum_score,
            hidden_gem = excluded.hidden_gem,
            motivated_seller = excluded.motivated_seller,
            reasons_json = excluded.reasons_json,
            components_json = excluded.components_json
        """,
        (
            score["listing_id"],
            score["scored_at"],
            score["score_version"],
            score["fit_score"],
            components["location_score"],
            components["travel_score"],
            components["nature_water_score"],
            components["privacy_score"],
            components["rental_score"],
            components["value_score"],
            components["momentum_score"],
            1 if score["hidden_gem"] else 0,
            1 if score["motivated_seller"] else 0,
            json.dumps(score["reasons"], ensure_ascii=False),
            json.dumps(components, ensure_ascii=False),
        ),
    )


def score_all(conn, prefs: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    prefs = prefs or preference_store.load_preferences()
    listings = load_active_listings(conn)
    medians = medians_for(listings)
    feedback_map = load_feedback_map(conn)
    scores = [score_listing(listing, prefs, medians, feedback_map) for listing in listings]
    for listing, score in zip(listings, scores):
        upsert_score(conn, score)
        flood_row = conn.execute(
            "SELECT source FROM flood_risk WHERE listing_id = ?",
            (listing["listing_id"],),
        ).fetchone()
        if flood_row is None or str(flood_row["source"]).startswith("pending_"):
            flood_risk.upsert_placeholder(conn, listing)
    conn.commit()
    return scores


def create_recommendation_run(conn, run_type: str, prefs: dict[str, Any]) -> int:
    cur = conn.execute(
        """
        INSERT INTO recommendation_runs (
            generated_at, run_type, status, message, preferences_json, item_count
        )
        VALUES (?, ?, ?, ?, ?, 0)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            run_type,
            "running",
            "Generating recommendations",
            json.dumps(prefs, ensure_ascii=False, sort_keys=True),
        ),
    )
    return int(cur.lastrowid)


def scored_rows(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT l.*, s.fit_score, s.location_score, s.travel_score, s.nature_water_score,
               s.privacy_score, s.rental_score, s.value_score, s.momentum_score,
               s.hidden_gem, s.motivated_seller, s.reasons_json, s.components_json,
               f.warning_level AS flood_warning_level,
               f.warning_text AS flood_warning_text,
               f.source AS flood_source,
               f.trigger_json AS flood_trigger_json,
               f.last_checked_at AS flood_last_checked_at
        FROM listings l
        JOIN listing_scores s ON s.listing_id = l.listing_id
        LEFT JOIN flood_risk f ON f.listing_id = l.listing_id
        WHERE l.status = 'active'
        """
    ).fetchall()
    return [decorate_listing(row_to_dict(row)) for row in rows]


def first_image_url(raw: dict[str, Any]) -> str | None:
    images = raw.get("images")
    if not isinstance(images, list):
        return None
    for image in images:
        if isinstance(image, dict) and image.get("url"):
            return str(image["url"])
    return None


def parse_open_house(value: str | None) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def has_future_open_house(item: dict[str, Any]) -> bool:
    parsed = parse_open_house(item.get("open_house"))
    if parsed is None:
        return False
    return parsed >= datetime.now(timezone.utc)


def decorate_listing(item: dict[str, Any]) -> dict[str, Any]:
    item["reasons"] = parse_json(item.pop("reasons_json", None), [])
    item["score_components"] = parse_json(item.pop("components_json", None), {})
    raw = raw_for(item)
    item["open_house"] = raw.get("openHouse") or None
    item["open_house_is_future"] = has_future_open_house(item)
    item["image_url"] = first_image_url(raw)
    item["image_count"] = len(raw.get("images") or []) if isinstance(raw.get("images"), list) else 0
    item["lot_size"] = raw.get("lotSize")
    item["views"] = raw.get("views")
    trigger = parse_json(item.pop("flood_trigger_json", None), {})
    item["flood_risk"] = {
        "warning_level": item.pop("flood_warning_level", None),
        "warning_text": item.pop("flood_warning_text", None),
        "source": item.pop("flood_source", None),
        "last_checked_at": item.pop("flood_last_checked_at", None),
        "details": trigger,
        "elevation_m": trigger.get("elevation_m") if isinstance(trigger, dict) else None,
        "low_lying_level": trigger.get("low_lying_level") if isinstance(trigger, dict) else None,
        "historical_flooding": trigger.get("historical_flooding") if isinstance(trigger, dict) else None,
    }
    item["hidden_gem"] = bool(item["hidden_gem"])
    item["motivated_seller"] = bool(item["motivated_seller"])
    return item


def price_drop_listing_ids(conn) -> set[str]:
    since = (date.today() - timedelta(days=60)).isoformat()
    rows = conn.execute(
        """
        SELECT DISTINCT listing_id
        FROM events
        WHERE event_type = 'PRICE_DROP' AND event_date >= ?
        UNION
        SELECT listing_id
        FROM listings
        WHERE last_price_drop_date IS NOT NULL
        """,
        (since,),
    ).fetchall()
    return {str(row["listing_id"]) for row in rows}


STOPWORDS = {
    "og", "eller", "men", "med", "uden", "som", "der", "det", "den", "de", "en", "et",
    "vi", "vil", "gerne", "have", "leder", "efter", "søger", "soeger", "på", "pa",
    "til", "for", "fra", "i", "om", "at", "er", "skal", "må", "maa", "meget",
}


def search_terms(prefs: dict[str, Any]) -> list[str]:
    search = prefs.get("search", {})
    terms: list[str] = []
    for key in ("description",):
        terms.extend(re.findall(r"[\wæøåÆØÅ-]{3,}", str(search.get(key) or "").lower()))
    for key in ("positive_keywords",):
        values = search.get(key) or []
        if isinstance(values, list):
            terms.extend(str(value).lower() for value in values)
    cleaned = []
    for term in terms:
        term = term.strip(".,;:!?()[]{}\"'")
        if len(term) >= 3 and term not in STOPWORDS and term not in cleaned:
            cleaned.append(term)
    return cleaned[:30]


def ai_highlight_score(item: dict[str, Any], prefs: dict[str, Any]) -> tuple[float, list[str]]:
    terms = search_terms(prefs)
    if not terms:
        return 0, []

    raw = raw_for(item)
    blob = text_blob(item, raw)
    blob = f"{blob} {item.get('region') or ''} {item.get('address') or ''}".lower()
    matched = [term for term in terms if term in blob]

    score = len(matched) * 10
    if item.get("nature_water_score", 0) >= 75:
        score += 15
    if item.get("privacy_score", 0) >= 70:
        score += 10
    if item.get("value_score", 0) >= 70:
        score += 10
    if item.get("fit_score", 0) >= prefs.get("interest_threshold", 68):
        score += 15

    reasons = []
    if matched:
        reasons.append("Matcher søgeteksten: " + ", ".join(matched[:6]) + ".")
    if item.get("nature_water_score", 0) >= 75:
        reasons.append("Passer til ønsket om vand, natur eller rolige omgivelser.")
    if item.get("privacy_score", 0) >= 70:
        reasons.append("Har tegn på privatliv eller god grundstørrelse.")
    if item.get("value_score", 0) >= 70:
        reasons.append("Ser prismæssigt fornuftig ud relativt til området.")
    return clamp(score), reasons


def matches_preference_filters(item: dict[str, Any], prefs: dict[str, Any]) -> bool:
    filters = prefs.get("filters", {})
    checks = (
        ("price_min", "asking_price", lambda actual, expected: actual >= expected),
        ("price_max", "asking_price", lambda actual, expected: actual <= expected),
        ("size_min", "size_m2", lambda actual, expected: actual >= expected),
        ("size_max", "size_m2", lambda actual, expected: actual <= expected),
        ("rooms_min", "rooms", lambda actual, expected: actual >= expected),
        ("lot_size_min", "lot_size", lambda actual, expected: actual >= expected),
        ("days_on_market_max", "days_on_market", lambda actual, expected: actual <= expected),
        ("price_per_m2_max", "price_per_m2", lambda actual, expected: actual <= expected),
    )
    for filter_key, item_key, test in checks:
        expected = filters.get(filter_key)
        actual = item.get(item_key)
        if expected not in ("", None) and actual not in ("", None):
            if not test(float(actual), float(expected)):
                return False

    regions = filters.get("regions") or []
    if regions and item.get("region") and item["region"] not in regions:
        return False

    energy_ratings = [str(value).upper() for value in filters.get("energy_ratings") or []]
    if energy_ratings and str(item.get("energy_rating") or "").upper() not in energy_ratings:
        return False

    postal_codes = [str(value).strip() for value in filters.get("postal_codes") or [] if str(value).strip()]
    if postal_codes and not any(str(item.get("postal_code") or "").startswith(prefix) for prefix in postal_codes):
        return False

    if filters.get("must_have_image") and not item.get("image_url"):
        return False
    return True


def merge_unique(*groups: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    merged: list[dict[str, Any]] = []
    for group in groups:
        for item in group:
            listing_id = str(item["listing_id"])
            if listing_id in seen:
                continue
            seen.add(listing_id)
            merged.append(item)
            if len(merged) >= limit:
                return merged
    return merged


def recent_daily_listing_ids(conn, days: int = 30) -> set[str]:
    """Listings already shown on the daily shortlist recently.

    The daily list is meant to help Jeppe see *different* houses over time, not
    simply repeat the highest-scoring five. Keep history in recommendation_items
    so previous /today dates remain browsable, but avoid reusing recent daily
    picks when generating a new run.
    """
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    rows = conn.execute(
        """
        SELECT DISTINCT ri.listing_id
        FROM recommendation_items ri
        JOIN recommendation_runs r ON r.id = ri.run_id
        WHERE ri.category = 'daily'
          AND r.status = 'ok'
          AND r.generated_at >= ?
        """,
        (since,),
    ).fetchall()
    return {str(row["listing_id"]) for row in rows}


def diverse_daily_rows(rows: list[dict[str, Any]], limit: int, seen_ids: set[str] | None = None) -> list[dict[str, Any]]:
    seen_ids = seen_ids or set()
    sorted_rows = sorted(rows, key=lambda row: row["fit_score"], reverse=True)
    fresh_rows = [row for row in sorted_rows if str(row["listing_id"]) not in seen_ids]

    def pick_from(pool: list[dict[str, Any]]) -> list[dict[str, Any]]:
        north = [
            row for row in pool
            if (row.get("postal_code") or 0) >= 3000 and (row.get("postal_code") or 0) <= 3699
        ]
        budget = [
            row for row in pool
            if (row.get("asking_price") or 0) <= 3_000_000
        ]
        close = [
            row for row in pool
            if (row.get("score_components") or {}).get("estimated_public_transport_minutes")
            and (row["score_components"]["estimated_public_transport_minutes"] <= 120)
        ]
        price_value = [row for row in pool if (row.get("value_score") or 0) >= 65]
        return merge_unique(
            pool[:3],
            budget[:2],
            north[:2],
            close[:2],
            price_value[:2],
            pool,
            limit=limit,
        )

    fresh_selection = pick_from(fresh_rows)
    if len(fresh_selection) >= limit:
        return fresh_selection

    # Fallback: if the fresh pool is too small, fill with the strongest recent
    # repeats rather than returning fewer than five houses.
    return merge_unique(fresh_selection, pick_from(sorted_rows), limit=limit)


def category_items(conn, rows: list[dict[str, Any]], prefs: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    threshold = prefs.get("interest_threshold", 68)
    daily_limit = prefs.get("daily_limit", 10)
    weekly_limit = prefs.get("weekly_limit", 10)
    ai_limit = prefs.get("ai_highlights_limit", 10)
    rows = [row for row in rows if matches_preference_filters(row, prefs)]
    eligible = [row for row in rows if row["fit_score"] >= threshold]
    daily_candidates = [row for row in rows if row["fit_score"] >= threshold - 15]
    sorted_rows = sorted(eligible, key=lambda row: row["fit_score"], reverse=True)
    drop_ids = price_drop_listing_ids(conn)
    recently_seen_daily = recent_daily_listing_ids(conn)
    ai_rows = []
    for row in rows:
        ai_score, ai_reasons = ai_highlight_score(row, prefs)
        if ai_score >= 25:
            enriched = dict(row)
            enriched["ai_match_score"] = ai_score
            enriched["recommendation_reasons"] = ai_reasons
            enriched["reasons"] = ai_reasons + enriched.get("reasons", [])
            ai_rows.append(enriched)

    return {
        "daily": diverse_daily_rows(daily_candidates, daily_limit, recently_seen_daily),
        "weekly": sorted_rows[:weekly_limit],
        "ai_highlights": sorted(
            ai_rows,
            key=lambda row: (row["ai_match_score"], row["fit_score"]),
            reverse=True,
        )[:ai_limit],
        "price_drops": [
            row for row in sorted(rows, key=lambda row: row["fit_score"], reverse=True)
            if row["listing_id"] in drop_ids and row["fit_score"] >= threshold - 8
        ][:10],
        "hidden_gems": [
            row for row in sorted_rows
            if row["hidden_gem"]
        ][:10],
        "open_houses": [
            row for row in sorted(
                [row for row in rows if row.get("open_house") and row["open_house_is_future"] and row["fit_score"] >= threshold],
                key=lambda row: str(row.get("open_house") or ""),
            )
        ][:25],
    }


def insert_recommendation_items(conn, run_id: int, categories: dict[str, list[dict[str, Any]]]) -> int:
    count = 0
    now = datetime.now().isoformat(timespec="seconds")
    for category, items in categories.items():
        for index, item in enumerate(items, start=1):
            conn.execute(
                """
                INSERT INTO recommendation_items (
                    run_id, category, listing_id, rank, fit_score, reasons_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    category,
                    item["listing_id"],
                    index,
                    item["fit_score"],
                    json.dumps(item.get("reasons", []), ensure_ascii=False),
                    now,
                ),
            )
            count += 1
    return count


def generate(conn, run_type: str = "agent") -> dict[str, Any]:
    prefs = preference_store.load_preferences()
    score_all(conn, prefs)
    run_id = create_recommendation_run(conn, run_type, prefs)
    try:
        rows = scored_rows(conn)
        categories = category_items(conn, rows, prefs)
        item_count = insert_recommendation_items(conn, run_id, categories)
        conn.execute(
            """
            UPDATE recommendation_runs
            SET status = ?, message = ?, item_count = ?
            WHERE id = ?
            """,
            ("ok", "Recommendations generated", item_count, run_id),
        )
        conn.commit()
        return {"run_id": run_id, "item_count": item_count, "categories": categories}
    except Exception as exc:
        conn.execute(
            "UPDATE recommendation_runs SET status = ?, message = ? WHERE id = ?",
            ("error", str(exc), run_id),
        )
        conn.commit()
        raise


def latest_run_id(conn) -> int | None:
    row = conn.execute(
        "SELECT id FROM recommendation_runs WHERE status = 'ok' ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def daily_history_runs(conn, limit: int = 30) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT r.id, substr(r.generated_at, 1, 10) AS date, r.generated_at,
               COUNT(ri.id) AS item_count
        FROM recommendation_runs r
        JOIN recommendation_items ri ON ri.run_id = r.id AND ri.category = 'daily'
        WHERE r.status = 'ok'
          AND r.id IN (
            SELECT MAX(id)
            FROM recommendation_runs
            WHERE status = 'ok'
            GROUP BY substr(generated_at, 1, 10)
          )
        GROUP BY r.id
        ORDER BY r.generated_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def run_id_for_daily_date(conn, selected_date: str | None) -> int | None:
    if not selected_date:
        return latest_run_id(conn)
    row = conn.execute(
        """
        SELECT id
        FROM recommendation_runs
        WHERE status = 'ok' AND substr(generated_at, 1, 10) = ?
        ORDER BY id DESC
        LIMIT 1
        """,
        (selected_date,),
    ).fetchone()
    return int(row["id"]) if row else None


def public_daily_for_date(conn, selected_date: str | None = None, limit: int = 5) -> dict[str, Any]:
    run_id = run_id_for_daily_date(conn, selected_date)
    history = daily_history_runs(conn)
    if run_id is None:
        return {"date": selected_date, "run_id": None, "history": history, "items": []}
    run = conn.execute("SELECT id, generated_at FROM recommendation_runs WHERE id = ?", (run_id,)).fetchone()
    items = items_for_category(conn, "daily", run_id)[:limit]
    generated_at = run["generated_at"] if run else None
    return {
        "date": str(generated_at or selected_date or "")[:10] or selected_date,
        "generated_at": generated_at,
        "run_id": run_id,
        "history": history,
        "items": items,
    }


def latest_categories(conn) -> dict[str, list[dict[str, Any]]]:
    run_id = latest_run_id(conn)
    if run_id is None:
        return {"daily": [], "weekly": [], "ai_highlights": [], "price_drops": [], "hidden_gems": [], "open_houses": []}
    result: dict[str, list[dict[str, Any]]] = {}
    for category in ("daily", "weekly", "ai_highlights", "price_drops", "hidden_gems", "open_houses"):
        result[category] = items_for_category(conn, category, run_id)
    return result


def items_for_category(conn, category: str, run_id: int | None = None) -> list[dict[str, Any]]:
    run_id = run_id or latest_run_id(conn)
    if run_id is None:
        return []
    rows = conn.execute(
        """
        SELECT l.*, s.fit_score, s.location_score, s.travel_score, s.nature_water_score,
               s.privacy_score, s.rental_score, s.value_score, s.momentum_score,
               s.hidden_gem, s.motivated_seller, s.reasons_json, s.components_json,
               ri.rank, ri.reasons_json AS recommendation_reasons_json,
               f.warning_level AS flood_warning_level,
               f.warning_text AS flood_warning_text,
               f.source AS flood_source,
               f.trigger_json AS flood_trigger_json,
               f.last_checked_at AS flood_last_checked_at
        FROM recommendation_items ri
        JOIN listings l ON l.listing_id = ri.listing_id
        JOIN listing_scores s ON s.listing_id = ri.listing_id
        LEFT JOIN flood_risk f ON f.listing_id = ri.listing_id
        WHERE ri.run_id = ? AND ri.category = ?
        ORDER BY ri.rank
        """,
        (run_id, category),
    ).fetchall()
    items = []
    for row in rows:
        raw_item = row_to_dict(row)
        recommendation_reasons = parse_json(raw_item.pop("recommendation_reasons_json", None), [])
        item = decorate_listing(raw_item)
        item["recommendation_reasons"] = recommendation_reasons
        if recommendation_reasons:
            item["reasons"] = recommendation_reasons + [
                reason for reason in item.get("reasons", [])
                if reason not in recommendation_reasons
            ]
        items.append(item)
    return items


def listing_analysis(conn, listing_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT l.*, s.fit_score, s.location_score, s.travel_score, s.nature_water_score,
               s.privacy_score, s.rental_score, s.value_score, s.momentum_score,
               s.hidden_gem, s.motivated_seller, s.reasons_json, s.components_json,
               f.warning_level AS flood_warning_level,
               f.warning_text AS flood_warning_text,
               f.source AS flood_source,
               f.trigger_json AS flood_trigger_json,
               f.last_checked_at AS flood_last_checked_at
        FROM listings l
        LEFT JOIN listing_scores s ON s.listing_id = l.listing_id
        LEFT JOIN flood_risk f ON f.listing_id = l.listing_id
        WHERE l.listing_id = ?
        """,
        (listing_id,),
    ).fetchone()
    if row is None:
        return None
    item = decorate_listing(row_to_dict(row)) if row["fit_score"] is not None else row_to_dict(row)
    feedback = conn.execute(
        "SELECT feedback_type, note, created_at FROM feedback WHERE listing_id = ? ORDER BY id DESC",
        (listing_id,),
    ).fetchall()
    item["feedback"] = [row_to_dict(feedback_row) for feedback_row in feedback]
    item["watching"] = conn.execute(
        "SELECT 1 FROM watchlist WHERE listing_id = ?",
        (listing_id,),
    ).fetchone() is not None
    return item


def add_feedback(conn, listing_id: str, feedback_type: str, note: str | None = None) -> dict[str, Any]:
    prefs = preference_store.load_preferences()
    if feedback_type not in prefs.get("feedback_types", []):
        raise ValueError(f"Unsupported feedback_type: {feedback_type}")
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        "INSERT INTO feedback (listing_id, feedback_type, note, created_at) VALUES (?, ?, ?, ?)",
        (listing_id, feedback_type, note, now),
    )
    if feedback_type == "watch":
        set_watch(conn, listing_id, note)
    conn.commit()
    return {"listing_id": listing_id, "feedback_type": feedback_type, "note": note, "created_at": now}


def set_watch(conn, listing_id: str, note: str | None = None) -> dict[str, Any]:
    now = datetime.now().isoformat(timespec="seconds")
    conn.execute(
        """
        INSERT INTO watchlist (listing_id, note, created_at, updated_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(listing_id) DO UPDATE SET
            note = COALESCE(excluded.note, watchlist.note),
            updated_at = excluded.updated_at
        """,
        (listing_id, note, now, now),
    )
    conn.commit()
    return {"listing_id": listing_id, "watching": True, "note": note}


def delete_watch(conn, listing_id: str) -> dict[str, Any]:
    conn.execute("DELETE FROM watchlist WHERE listing_id = ?", (listing_id,))
    conn.commit()
    return {"listing_id": listing_id, "watching": False}


def watchlist(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT l.*, w.note AS watch_note, w.created_at AS watched_at,
               s.fit_score, s.location_score, s.travel_score, s.nature_water_score,
               s.privacy_score, s.rental_score, s.value_score, s.momentum_score,
               s.hidden_gem, s.motivated_seller, s.reasons_json, s.components_json,
               f.warning_level AS flood_warning_level,
               f.warning_text AS flood_warning_text,
               f.source AS flood_source,
               f.trigger_json AS flood_trigger_json,
               f.last_checked_at AS flood_last_checked_at
        FROM watchlist w
        JOIN listings l ON l.listing_id = w.listing_id
        LEFT JOIN listing_scores s ON s.listing_id = w.listing_id
        LEFT JOIN flood_risk f ON f.listing_id = w.listing_id
        ORDER BY w.updated_at DESC
        """
    ).fetchall()
    items = []
    for row in rows:
        item = row_to_dict(row)
        if item.get("fit_score") is not None:
            item = decorate_listing(item)
        items.append(item)
    return items


def map_listings(conn, limit: int = 2000) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT l.*, s.fit_score, s.hidden_gem, s.motivated_seller,
               s.reasons_json, s.components_json,
               f.warning_level AS flood_warning_level,
               f.warning_text AS flood_warning_text,
               f.source AS flood_source,
               f.trigger_json AS flood_trigger_json,
               f.last_checked_at AS flood_last_checked_at
        FROM listings l
        LEFT JOIN listing_scores s ON s.listing_id = l.listing_id
        LEFT JOIN flood_risk f ON f.listing_id = l.listing_id
        WHERE l.status = 'active'
          AND l.latitude IS NOT NULL
          AND l.longitude IS NOT NULL
        ORDER BY COALESCE(s.fit_score, 0) DESC, l.asking_price ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    items = []
    for row in rows:
        item = row_to_dict(row)
        raw = raw_for(item)
        item.pop("raw_json", None)
        item["image_url"] = first_image_url(raw)
        item["open_house"] = raw.get("openHouse") or None
        item["open_house_is_future"] = has_future_open_house(item)
        item["lot_size"] = raw.get("lotSize")
        reasons = parse_json(item.pop("reasons_json", None), [])
        components = parse_json(item.pop("components_json", None), {})
        flood_trigger = parse_json(item.pop("flood_trigger_json", None), {})
        item["reasons"] = reasons[:3]
        item["flood_risk"] = {
            "warning_level": item.pop("flood_warning_level", None),
            "warning_text": item.pop("flood_warning_text", None),
            "source": item.pop("flood_source", None),
            "last_checked_at": item.pop("flood_last_checked_at", None),
            "details": flood_trigger,
            "elevation_m": flood_trigger.get("elevation_m") if isinstance(flood_trigger, dict) else None,
            "low_lying_level": flood_trigger.get("low_lying_level") if isinstance(flood_trigger, dict) else None,
            "historical_flooding": flood_trigger.get("historical_flooding") if isinstance(flood_trigger, dict) else None,
        }
        item["score_components"] = {
            "estimated_public_transport_minutes": components.get("estimated_public_transport_minutes"),
            "estimated_car_minutes": components.get("estimated_car_minutes"),
            "area_research_id": components.get("area_research_id"),
            "area_research_name": components.get("area_research_name"),
            "area_research_score": components.get("area_research_score"),
            "area_research_adjustment": components.get("area_research_adjustment"),
        }
        item["hidden_gem"] = bool(item.get("hidden_gem"))
        item["motivated_seller"] = bool(item.get("motivated_seller"))
        items.append(item)
    return items
