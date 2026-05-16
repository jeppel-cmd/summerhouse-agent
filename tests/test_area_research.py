import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import area_research
import preferences
import recommendations


def test_area_research_loads_danish_opinionated_bridge_connected_profiles():
    areas = area_research.load_area_profiles()

    assert len(areas) >= 8
    assert all(area["language"] == "da" for area in areas)
    assert all(area["access_scope"] == "sjælland_bridge_connected" for area in areas)
    assert all(area["opinionated_take"].strip() for area in areas)
    assert all(area["sources"] for area in areas)
    assert any(area.get("hidden_gem_score", 0) >= 80 for area in areas)


def test_area_profile_matches_by_postal_code_and_area_score_affects_listing_score():
    medians = {"prefix:42": 24_000, "region:Region Sjælland": 24_000}
    base_prefs = preferences.load_preferences()
    listing = {
        "listing_id": "area-test-1",
        "address": "Strandvej 1",
        "city": "Stillinge Strand",
        "postal_code": 4200,
        "region": "Region Sjælland",
        "asking_price": 2_300_000,
        "price_per_m2": 24_000,
        "size_m2": 90,
        "rooms": 4,
        "energy_rating": None,
        "days_on_market": 20,
        "listing_url": "https://example.test/area",
        "latitude": 55.41,
        "longitude": 11.19,
        "last_price_drop_date": None,
        "raw_json": "{}",
    }

    matched = area_research.match_area_profile(listing)
    assert matched is not None
    assert matched["id"] == "stillinge-kongsmark"

    scored = recommendations.score_listing(listing, base_prefs, medians, {})
    assert scored["components"]["area_research_score"] >= 80
    assert scored["components"]["area_research_adjustment"] > 0
    assert any("område" in reason.lower() for reason in scored["reasons"])


def test_preferences_include_readable_wishes_note_for_agent_research():
    prefs = preferences.load_preferences()

    assert "wishes_note" in prefs["search"]
    assert "Sjælland" in prefs["search"]["wishes_note"]
    assert "færge" in prefs["search"]["wishes_note"].lower()
