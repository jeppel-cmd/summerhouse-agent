import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import recommendations


def listing(**overrides):
    raw = {
        "lotSize": 900,
        "views": 20,
        "rooms": overrides.get("rooms", 4),
    }
    raw.update(overrides.pop("raw", {}))
    data = {
        "listing_id": "test-1",
        "address": "Strandvej 1",
        "city": "Nykøbing Sj",
        "postal_code": 4500,
        "region": "Region Sjælland",
        "asking_price": 2_300_000,
        "price_per_m2": 25_000,
        "size_m2": 90,
        "rooms": 4,
        "energy_rating": None,
        "days_on_market": 30,
        "listing_url": "https://example.test/1",
        "latitude": 55.92,
        "longitude": 11.67,
        "last_price_drop_date": None,
        "raw_json": json.dumps(raw),
    }
    data.update(overrides)
    return data


def prefs():
    return {
        "regions": {"include_hovedstaden": True, "avoid_ferry": True},
        "budget": {
            "ideal_min": 2_000_000,
            "ideal_max": 2_500_000,
            "move_in_ready_max": 3_000_000,
            "renovation_max": 2_000_000,
        },
        "house": {"bedrooms_min": 3},
        "travel": {"max_public_transport_minutes": 120, "warn_public_transport_minutes": 135},
        "services": {"max_supermarket_car_minutes": 20},
    }


def test_ideal_price_scores_better_than_over_budget():
    medians = {"prefix:45": 25_000, "region:Region Sjælland": 25_000}
    ideal = recommendations.score_listing(listing(asking_price=2_300_000), prefs(), medians, {})
    over = recommendations.score_listing(listing(asking_price=3_250_000), prefs(), medians, {})

    assert ideal["components"]["price_fit_score"] > over["components"]["price_fit_score"]
    assert ideal["fit_score"] > over["fit_score"]
    assert any("idealbudget" in reason.lower() for reason in ideal["reasons"])
    assert any("over 3 mio" in reason.lower() for reason in over["reasons"])


def test_below_ideal_price_is_positive_not_a_penalty_when_other_factors_match():
    medians = {"prefix:45": 25_000, "region:Region Sjælland": 25_000}
    ideal = recommendations.score_listing(listing(asking_price=2_300_000), prefs(), medians, {})
    below = recommendations.score_listing(listing(asking_price=1_700_000), prefs(), medians, {})

    assert below["components"]["price_fit_score"] >= ideal["components"]["price_fit_score"]
    assert below["fit_score"] >= ideal["fit_score"]
    assert any("under idealbudgettet" in reason.lower() for reason in below["reasons"])


def test_renovation_project_can_be_interesting_under_two_million():
    medians = {"prefix:45": 25_000, "region:Region Sjælland": 25_000}
    raw = {"description": "Renoveringsprojekt med nyt tag og stor grund tæt på skov"}
    score = recommendations.score_listing(
        listing(asking_price=1_750_000, price_per_m2=18_000, raw=raw),
        prefs(),
        medians,
        {},
    )

    assert score["components"]["price_fit_score"] >= 75
    assert any("renovering" in reason.lower() for reason in score["reasons"])


def test_bornholm_ferry_is_not_recommended_even_if_cheap():
    medians = {"prefix:37": 18_000, "region:Region Hovedstaden": 18_000}
    score = recommendations.score_listing(
        listing(postal_code=3790, city="Hasle", asking_price=750_000, price_per_m2=12_000),
        prefs(),
        medians,
        {},
    )

    assert score["fit_score"] < 45
    assert score["components"]["location_score"] <= 10
    assert any("færge" in reason.lower() for reason in score["reasons"])


def test_three_bedrooms_is_interpreted_conservatively_from_rooms_field():
    medians = {"prefix:45": 25_000, "region:Region Sjælland": 25_000}
    enough = recommendations.score_listing(listing(rooms=4), prefs(), medians, {})
    uncertain = recommendations.score_listing(listing(rooms=3), prefs(), medians, {})

    assert enough["components"]["bedroom_score"] > uncertain["components"]["bedroom_score"]
    assert any("3 soveværelser" in reason.lower() for reason in uncertain["reasons"])


def test_move_in_ready_budget_up_to_three_million_is_not_penalized_like_over_budget():
    medians = {"prefix:45": 25_000, "region:Region Sjælland": 25_000}
    ideal = recommendations.score_listing(listing(asking_price=2_300_000), prefs(), medians, {})
    move_in_ready = recommendations.score_listing(listing(asking_price=2_800_000), prefs(), medians, {})
    over_budget = recommendations.score_listing(listing(asking_price=3_250_000), prefs(), medians, {})

    assert move_in_ready["components"]["price_fit_score"] >= ideal["components"]["price_fit_score"] - 5
    assert move_in_ready["components"]["price_fit_score"] >= 90
    assert move_in_ready["components"]["price_fit_score"] > over_budget["components"]["price_fit_score"]
    assert any("maks. 3 mio" in reason.lower() for reason in move_in_ready["reasons"])


def test_public_transport_near_two_hours_is_penalized_more_than_close_hops():
    medians = {"prefix:36": 25_000, "region:Region Hovedstaden": 25_000}
    score = recommendations.score_listing(
        listing(
            postal_code=3630,
            city="Jægerspris",
            latitude=55.92216,
            longitude=11.92616,
        ),
        prefs(),
        medians,
        {},
    )

    public_minutes = score["components"]["estimated_public_transport_minutes"]
    assert public_minutes is not None and 105 <= public_minutes <= 120
    assert score["components"]["travel_score"] <= 70
    assert any("offentlig transport" in reason.lower() for reason in score["reasons"])


def test_slightly_long_public_transport_warns_without_hard_excluding():
    medians = {"prefix:45": 25_000, "region:Region Sjælland": 25_000}
    score = recommendations.score_listing(
        listing(latitude=55.8, longitude=11.75),
        prefs(),
        medians,
        {},
    )

    public_minutes = score["components"]["estimated_public_transport_minutes"]
    assert public_minutes is not None and public_minutes > 120
    assert 25 <= score["components"]["travel_score"] <= 45
    assert any("lidt over" in reason.lower() or "over 2 timer" in reason.lower() for reason in score["reasons"])
