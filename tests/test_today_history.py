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
    assert [entry["date"] for entry in payload["history"]] == ["2026-05-17", "2026-05-16"]
    assert [entry["id"] for entry in payload["history"]] == [3, 2]
