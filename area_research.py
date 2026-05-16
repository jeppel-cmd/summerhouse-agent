from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

AREA_RESEARCH_PATH = Path("data/area_research.json")


def load_area_profiles(path: Path = AREA_RESEARCH_PATH) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")
    return [profile for profile in data if isinstance(profile, dict)]


def _postal_matches(postal: int | None, profile: dict[str, Any]) -> bool:
    if postal is None:
        return False
    for start, end in profile.get("postal_ranges", []):
        if int(start) <= postal <= int(end):
            return True
    return False


def _city_matches(city: str, profile: dict[str, Any]) -> bool:
    haystack = city.lower()
    for term in profile.get("match_terms", []):
        if str(term).lower() in haystack:
            return True
    return False


def match_area_profile(listing: dict[str, Any], profiles: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    profiles = profiles if profiles is not None else load_area_profiles()
    postal_value = listing.get("postal_code")
    try:
        postal = int(postal_value) if postal_value not in (None, "") else None
    except (TypeError, ValueError):
        postal = None
    city = str(listing.get("city") or "")

    candidates: list[dict[str, Any]] = []
    for profile in profiles:
        if _postal_matches(postal, profile) or _city_matches(city, profile):
            candidates.append(profile)
    if not candidates:
        return None
    # Prefer more specific / more opinionated matches first.
    return max(candidates, key=lambda item: (item.get("hidden_gem_score", 0), item.get("area_fit_score", 0)))


def area_adjustment(profile: dict[str, Any] | None) -> tuple[float, float]:
    """Return (area_score, fit_adjustment) where adjustment is capped at +/-15 points."""
    if not profile:
        return 50.0, 0.0
    area_score = float(profile.get("area_fit_score", 50))
    adjustment = max(-15.0, min(15.0, (area_score - 50.0) * 0.3))
    return area_score, round(adjustment, 1)


def public_profiles(path: Path = AREA_RESEARCH_PATH) -> list[dict[str, Any]]:
    profiles = deepcopy(load_area_profiles(path))
    return sorted(profiles, key=lambda item: item.get("area_fit_score", 0), reverse=True)
