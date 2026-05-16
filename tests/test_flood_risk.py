import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import flood_risk


def listing(**overrides):
    data = {
        "listing_id": "geo-1",
        "address": "Strandvej 1",
        "postal_code": 4500,
        "city": "Nykøbing Sj",
        "latitude": 55.92,
        "longitude": 11.67,
    }
    data.update(overrides)
    return data


def test_low_elevation_flags_high_even_when_coast_reference_is_not_close(monkeypatch):
    monkeypatch.setattr(
        flood_risk,
        "nearest_kamp_coast_point",
        lambda lat, lon: {"distance_km": 8.2, "coast_name": "Testkyst", "storm_surge_100y_cm": 160},
    )
    monkeypatch.setattr(flood_risk, "elevation_m", lambda lat, lon: 1.4)

    warning = flood_risk.assess_listing(listing())

    assert warning["warning_level"] == "high"
    assert "1.4 m over havet" in warning["warning_text"]
    assert warning["trigger_json"]["elevation_m"] == 1.4
    assert warning["trigger_json"]["low_lying_level"] == "high"


def test_dingeo_address_url_is_included_for_historical_manual_check():
    hint = flood_risk.historical_flooding_hint(listing())

    assert hint["status"] == "manual_check_required"
    assert "dingeo.dk/adresse/4500-nyk" in hint["dingeo_url"]
    assert hint["observed_flooding"] is None
