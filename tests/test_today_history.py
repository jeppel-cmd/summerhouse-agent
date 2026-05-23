from __future__ import annotations

import json
import sqlite3

import recommendations


def setup_history_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE recommendation_runs (
            id INTEGER PRIMARY KEY,
            generated_at TEXT NOT NULL,
            run_type TEXT,
            status TEXT NOT NULL,
            message TEXT,
            preferences_json TEXT,
            item_count INTEGER
        );
        CREATE TABLE recommendation_items (
            id INTEGER PRIMARY KEY,
            run_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            listing_id TEXT NOT NULL,
            rank INTEGER NOT NULL,
            fit_score REAL,
            reasons_json TEXT,
            created_at TEXT
        );
        CREATE TABLE listings (
            listing_id TEXT PRIMARY KEY,
            address TEXT,
            city TEXT,
            postal_code INTEGER,
            region TEXT,
            asking_price INTEGER,
            size_m2 REAL,
            rooms REAL,
            price_per_m2 INTEGER,
            raw_json TEXT,
            status TEXT
        );
        CREATE TABLE listing_scores (
            listing_id TEXT PRIMARY KEY,
            fit_score REAL,
            location_score REAL,
            travel_score REAL,
            nature_water_score REAL,
            privacy_score REAL,
            rental_score REAL,
            value_score REAL,
            momentum_score REAL,
            hidden_gem INTEGER,
            motivated_seller INTEGER,
            reasons_json TEXT,
            components_json TEXT
        );
        CREATE TABLE flood_risk (
            listing_id TEXT PRIMARY KEY,
            warning_level TEXT,
            warning_text TEXT,
            source TEXT,
            trigger_json TEXT,
            last_checked_at TEXT
        );
        """
    )
    for listing_id, score in [("a", 91), ("b", 88), ("c", 82)]:
        conn.execute(
            "INSERT INTO listings VALUES (?, ?, ?, 4500, 'Sjælland', 2000000, 80, 4, 25000, ?, 'active')",
            (listing_id, f"Testvej {listing_id}", "Rørvig", json.dumps({"images": []})),
        )
        conn.execute(
            "INSERT INTO listing_scores VALUES (?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, ?, ?)",
            (listing_id, score, json.dumps(["Godt match"]), json.dumps({})),
        )
    runs = [(1, "2026-05-16T09:00:00"), (2, "2026-05-16T18:00:00"), (3, "2026-05-17T10:00:00")]
    for run_id, generated_at in runs:
        conn.execute("INSERT INTO recommendation_runs VALUES (?, ?, 'agent', 'ok', 'ok', '{}', 3)", (run_id, generated_at))
        for rank, listing_id in enumerate(["a", "b", "c"], start=1):
            conn.execute(
                "INSERT INTO recommendation_items (run_id, category, listing_id, rank, fit_score, reasons_json, created_at) VALUES (?, 'daily', ?, ?, 90, '[]', ?)",
                (run_id, listing_id, rank, generated_at),
            )
    conn.commit()
    return conn


def test_public_daily_for_date_returns_history_and_selected_day() -> None:
    conn = setup_history_db()
    payload = recommendations.public_daily_for_date(conn, "2026-05-16")

    assert payload["date"] == "2026-05-16"
    assert payload["run_id"] == 2
    assert len(payload["items"]) == 3
    assert payload["regions"] == []
    assert [entry["date"] for entry in payload["history"]] == ["2026-05-17", "2026-05-16"]
    assert [entry["id"] for entry in payload["history"]] == [3, 2]


def test_daily_region_for_covers_public_quadrants() -> None:
    assert recommendations.daily_region_for({"postal_code": 3100}) == "north"
    assert recommendations.daily_region_for({"postal_code": 4791}) == "south"
    assert recommendations.daily_region_for({"postal_code": 4671}) == "east"
    assert recommendations.daily_region_for({"postal_code": 4500}) == "west"
    assert recommendations.daily_region_for({"postal_code": 2791}) is None


def test_public_daily_for_date_returns_regional_sections_when_present() -> None:
    conn = setup_history_db()
    regional = [
        (3, "daily_north", "a", 1),
        (3, "daily_south", "b", 1),
        (3, "daily_east", "c", 1),
    ]
    for run_id, category, listing_id, rank in regional:
        conn.execute(
            "INSERT INTO recommendation_items (run_id, category, listing_id, rank, fit_score, reasons_json, created_at) VALUES (?, ?, ?, ?, 90, '[]', '2026-05-17T10:00:00')",
            (run_id, category, listing_id, rank),
        )
    conn.commit()

    payload = recommendations.public_daily_for_date(conn, "2026-05-17")

    assert [group["key"] for group in payload["regions"]] == ["north", "south", "east", "west"]
    assert [group["count"] for group in payload["regions"]] == [1, 1, 1, 0]
    assert payload["history"][0]["item_count"] == 3



def test_diverse_daily_rows_prefers_unseen_even_with_lower_scores() -> None:
    rows = [
        {
            "listing_id": "seen-high",
            "fit_score": 95,
            "postal_code": 4500,
            "asking_price": 2100000,
            "value_score": 80,
            "score_components": {"estimated_public_transport_minutes": 95},
        },
        {
            "listing_id": "fresh-lower",
            "fit_score": 73,
            "postal_code": 4560,
            "asking_price": 2400000,
            "value_score": 70,
            "score_components": {"estimated_public_transport_minutes": 110},
        },
    ]

    picked = recommendations.diverse_daily_rows(rows, limit=1, seen_ids={"seen-high"})

    assert [item["listing_id"] for item in picked] == ["fresh-lower"]


def test_diverse_daily_rows_can_cap_single_city_dominance() -> None:
    rows = [
        {
            "listing_id": f"j-{idx}",
            "fit_score": 100 - idx,
            "postal_code": 3630,
            "city": "Jægerspris",
            "asking_price": 1_500_000,
            "value_score": 80,
            "score_components": {"estimated_public_transport_minutes": 100},
        }
        for idx in range(4)
    ] + [
        {
            "listing_id": "gilleleje",
            "fit_score": 80,
            "postal_code": 3250,
            "city": "Gilleleje",
            "asking_price": 2_900_000,
            "value_score": 60,
            "score_components": {"estimated_public_transport_minutes": 113},
        },
        {
            "listing_id": "vejby",
            "fit_score": 78,
            "postal_code": 3210,
            "city": "Vejby",
            "asking_price": 2_500_000,
            "value_score": 58,
            "score_components": {"estimated_public_transport_minutes": 122},
        },
    ]

    picked = recommendations.diverse_daily_rows(rows, limit=5, max_per_locality=2)
    picked_ids = [item["listing_id"] for item in picked]

    assert picked_ids[:2] == ["j-0", "j-1"]
    assert "gilleleje" in picked_ids
    assert "vejby" in picked_ids
