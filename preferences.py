from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any


PREFERENCES_PATH = Path("preferences.json")


DEFAULT_PREFERENCES: dict[str, Any] = {
    "interest_threshold": 68,
    "daily_limit": 10,
    "weekly_limit": 10,
    "ai_highlights_limit": 10,
    "home_base": "Copenhagen Central Station",
    "filters": {
        "price_min": None,
        "price_max": None,
        "size_min": None,
        "size_max": None,
        "rooms_min": None,
        "lot_size_min": None,
        "days_on_market_max": None,
        "price_per_m2_max": None,
        "regions": ["Region Sjælland", "Region Hovedstaden"],
        "postal_codes": [],
        "energy_ratings": [],
        "must_have_image": True,
        "only_future_open_houses": True,
    },
    "search": {
        "description": (
            "Vi leder efter et indbydende sommerhus på Sjælland, gerne nær vand "
            "eller natur, med ro, privatliv, god familiebrug og fornuftig pris."
        ),
        "positive_keywords": [
            "strand",
            "hav",
            "fjord",
            "skov",
            "natur",
            "rolig",
            "familie",
            "privatliv",
        ],
        "negative_keywords": [
            "færge",
            "meget lang rejsetid",
        ],
    },
    "regions": {
        "prefer_sjaelland": True,
        "include_hovedstaden": True,
        "avoid_ferry": True,
    },
    "travel": {
        "max_public_transport_minutes": 120,
        "ideal_car_minutes_min": 60,
        "ideal_car_minutes_max": 90,
    },
    "signals": {
        "near_water": True,
        "peace_quiet": True,
        "privacy": True,
        "nature": True,
        "family_use": True,
        "rental_potential": True,
        "renovation_potential": "state_not_penalize",
        "motivated_seller_weight": "moderate",
    },
    "dealbreakers": {
        "ferry_required": False,
        "high_flood_risk": False,
        "poor_location": False,
    },
    "feedback_types": [
        "favorite",
        "like",
        "dislike",
    ],
}


def _merge_defaults(defaults: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(defaults)
    for key, value in current.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_defaults(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_preferences(path: Path = PREFERENCES_PATH) -> dict[str, Any]:
    if not path.exists():
        save_preferences(DEFAULT_PREFERENCES, path)
        return deepcopy(DEFAULT_PREFERENCES)

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    merged = _merge_defaults(DEFAULT_PREFERENCES, data)
    merged["feedback_types"] = DEFAULT_PREFERENCES["feedback_types"]
    return merged


def save_preferences(preferences: dict[str, Any], path: Path = PREFERENCES_PATH) -> dict[str, Any]:
    merged = _merge_defaults(DEFAULT_PREFERENCES, preferences)
    path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return merged
