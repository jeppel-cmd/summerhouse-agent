from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


DB_PATH = Path("data") / "boliga.sqlite"


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            status TEXT NOT NULL,
            message TEXT,
            fetched_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS listings (
            listing_id TEXT PRIMARY KEY,
            address TEXT,
            city TEXT,
            postal_code INTEGER,
            region TEXT,
            asking_price INTEGER,
            price_per_m2 INTEGER,
            size_m2 REAL,
            rooms REAL,
            year_built INTEGER,
            energy_rating TEXT,
            days_on_market INTEGER,
            listing_url TEXT,
            latitude REAL,
            longitude REAL,
            first_seen_date TEXT NOT NULL,
            last_seen_date TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            last_price_drop_date TEXT,
            raw_json TEXT
        );

        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,
            seen_date TEXT NOT NULL,
            asking_price INTEGER,
            price_per_m2 INTEGER,
            UNIQUE (listing_id, seen_date, asking_price),
            FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
        );

        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,
            run_id INTEGER NOT NULL,
            event_date TEXT NOT NULL,
            event_type TEXT NOT NULL,
            old_price INTEGER,
            new_price INTEGER,
            delta_dkk INTEGER,
            delta_percent REAL,
            FOREIGN KEY (listing_id) REFERENCES listings(listing_id),
            FOREIGN KEY (run_id) REFERENCES runs(id)
        );

        CREATE TABLE IF NOT EXISTS listing_scores (
            listing_id TEXT PRIMARY KEY,
            scored_at TEXT NOT NULL,
            score_version TEXT NOT NULL,
            fit_score REAL NOT NULL,
            location_score REAL NOT NULL,
            travel_score REAL NOT NULL,
            nature_water_score REAL NOT NULL,
            privacy_score REAL NOT NULL,
            rental_score REAL NOT NULL,
            value_score REAL NOT NULL,
            momentum_score REAL NOT NULL,
            hidden_gem INTEGER NOT NULL DEFAULT 0,
            motivated_seller INTEGER NOT NULL DEFAULT 0,
            reasons_json TEXT NOT NULL,
            components_json TEXT NOT NULL,
            FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
        );

        CREATE TABLE IF NOT EXISTS recommendation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            generated_at TEXT NOT NULL,
            run_type TEXT NOT NULL,
            status TEXT NOT NULL,
            message TEXT,
            preferences_json TEXT,
            item_count INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS recommendation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            listing_id TEXT NOT NULL,
            rank INTEGER NOT NULL,
            fit_score REAL NOT NULL,
            reasons_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE (run_id, category, listing_id),
            FOREIGN KEY (run_id) REFERENCES recommendation_runs(id),
            FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
        );

        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            listing_id TEXT NOT NULL,
            feedback_type TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
        );

        CREATE TABLE IF NOT EXISTS watchlist (
            listing_id TEXT PRIMARY KEY,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
        );

        CREATE TABLE IF NOT EXISTS flood_risk (
            listing_id TEXT PRIMARY KEY,
            warning_level TEXT NOT NULL DEFAULT 'unknown',
            warning_text TEXT,
            source TEXT,
            trigger_json TEXT,
            last_checked_at TEXT,
            FOREIGN KEY (listing_id) REFERENCES listings(listing_id)
        );
        """
    )
    conn.commit()


def row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def start_run(conn: sqlite3.Connection) -> int:
    cur = conn.execute(
        "INSERT INTO runs (started_at, status) VALUES (?, ?)",
        (datetime.now().isoformat(timespec="seconds"), "running"),
    )
    conn.commit()
    return int(cur.lastrowid)


def finish_run(conn: sqlite3.Connection, run_id: int, status: str, message: str, fetched_count: int) -> None:
    conn.execute(
        """
        UPDATE runs
        SET finished_at = ?, status = ?, message = ?, fetched_count = ?
        WHERE id = ?
        """,
        (datetime.now().isoformat(timespec="seconds"), status, message, fetched_count, run_id),
    )
    conn.commit()


def insert_event(
    conn: sqlite3.Connection,
    run_id: int,
    listing_id: str,
    event_type: str,
    old_price: int | None = None,
    new_price: int | None = None,
) -> None:
    delta = None
    delta_percent = None
    if old_price is not None and new_price is not None:
        delta = new_price - old_price
        if old_price:
            delta_percent = round((delta / old_price) * 100, 2)

    conn.execute(
        """
        INSERT INTO events (
            listing_id, run_id, event_date, event_type,
            old_price, new_price, delta_dkk, delta_percent
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (listing_id, run_id, date.today().isoformat(), event_type, old_price, new_price, delta, delta_percent),
    )


def sync_listings(conn: sqlite3.Connection, listings: list[dict[str, Any]], run_id: int) -> dict[str, int]:
    today = date.today().isoformat()
    counts = {"new": 0, "price_drop": 0, "price_increase": 0, "gone": 0, "active": len(listings)}
    seen_ids = {listing["listing_id"] for listing in listings}

    for listing in listings:
        existing = conn.execute(
            "SELECT listing_id, asking_price, first_seen_date FROM listings WHERE listing_id = ?",
            (listing["listing_id"],),
        ).fetchone()
        pending_event: tuple[str, int | None, int | None] | None = None

        if existing is None:
            counts["new"] += 1
            pending_event = ("NEW", None, listing["asking_price"])
            first_seen = today
            last_price_drop_date = None
        else:
            first_seen = existing["first_seen_date"]
            old_price = existing["asking_price"]
            new_price = listing["asking_price"]
            last_price_drop_date = None
            if old_price is not None and new_price is not None and old_price != new_price:
                if new_price < old_price:
                    counts["price_drop"] += 1
                    last_price_drop_date = today
                    pending_event = ("PRICE_DROP", old_price, new_price)
                else:
                    counts["price_increase"] += 1
                    pending_event = ("PRICE_INCREASE", old_price, new_price)

        conn.execute(
            """
            INSERT INTO listings (
                listing_id, address, city, postal_code, region, asking_price,
                price_per_m2, size_m2, rooms, year_built, energy_rating,
                days_on_market, listing_url, latitude, longitude,
                first_seen_date, last_seen_date, status, last_price_drop_date, raw_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(listing_id) DO UPDATE SET
                address = excluded.address,
                city = excluded.city,
                postal_code = excluded.postal_code,
                region = excluded.region,
                asking_price = excluded.asking_price,
                price_per_m2 = excluded.price_per_m2,
                size_m2 = excluded.size_m2,
                rooms = excluded.rooms,
                year_built = excluded.year_built,
                energy_rating = excluded.energy_rating,
                days_on_market = excluded.days_on_market,
                listing_url = excluded.listing_url,
                latitude = excluded.latitude,
                longitude = excluded.longitude,
                last_seen_date = excluded.last_seen_date,
                status = 'active',
                last_price_drop_date = COALESCE(excluded.last_price_drop_date, listings.last_price_drop_date),
                raw_json = excluded.raw_json
            """,
            (
                listing["listing_id"],
                listing.get("address"),
                listing.get("city"),
                listing.get("postal_code"),
                listing.get("region"),
                listing.get("asking_price"),
                listing.get("price_per_m2"),
                listing.get("size_m2"),
                listing.get("rooms"),
                listing.get("year_built"),
                listing.get("energy_rating"),
                listing.get("days_on_market"),
                listing.get("listing_url"),
                listing.get("latitude"),
                listing.get("longitude"),
                first_seen,
                today,
                last_price_drop_date,
                json.dumps(listing.get("raw"), ensure_ascii=False),
            ),
        )

        conn.execute(
            """
            INSERT OR IGNORE INTO price_history (listing_id, seen_date, asking_price, price_per_m2)
            VALUES (?, ?, ?, ?)
            """,
            (listing["listing_id"], today, listing.get("asking_price"), listing.get("price_per_m2")),
        )

        if pending_event:
            event_type, old_price, new_price = pending_event
            insert_event(conn, run_id, listing["listing_id"], event_type, old_price, new_price)

    gone_rows = conn.execute("SELECT listing_id FROM listings WHERE status = 'active'").fetchall()
    for row in gone_rows:
        if row["listing_id"] not in seen_ids:
            counts["gone"] += 1
            conn.execute(
                "UPDATE listings SET status = 'gone', last_seen_date = ? WHERE listing_id = ?",
                (today, row["listing_id"]),
            )
            insert_event(conn, run_id, row["listing_id"], "GONE")

    conn.commit()
    return counts


def list_active(conn: sqlite3.Connection, filters: dict[str, Any]) -> list[dict[str, Any]]:
    clauses = ["status = 'active'"]
    params: list[Any] = []

    for field, op, value in (
        ("region", "=", filters.get("region")),
        ("energy_rating", "=", filters.get("energy_rating")),
        ("asking_price", ">=", filters.get("price_min")),
        ("asking_price", "<=", filters.get("price_max")),
        ("size_m2", ">=", filters.get("size_min")),
        ("size_m2", "<=", filters.get("size_max")),
        ("rooms", ">=", filters.get("rooms_min")),
        ("rooms", "<=", filters.get("rooms_max")),
        ("price_per_m2", ">=", filters.get("ppm_min")),
        ("price_per_m2", "<=", filters.get("ppm_max")),
        ("days_on_market", "<=", filters.get("days_on_market_max")),
    ):
        if value not in ("", None):
            clauses.append(f"{field} {op} ?")
            params.append(value)

    if filters.get("lot_size_min") not in ("", None):
        clauses.append("CAST(json_extract(raw_json, '$.lotSize') AS REAL) >= ?")
        params.append(filters["lot_size_min"])

    if filters.get("has_image"):
        clauses.append("json_array_length(json_extract(raw_json, '$.images')) > 0")

    rows = conn.execute(
        f"""
        SELECT *,
            CASE
                WHEN last_price_drop_date IS NOT NULL THEN 1 ELSE 0
            END AS has_price_drop,
            CASE
                WHEN days_on_market >= 60
                 AND last_price_drop_date >= date('now', '-30 day')
                THEN 1 ELSE 0
            END AS motivated_seller
        FROM listings
        WHERE {" AND ".join(clauses)}
        ORDER BY has_price_drop DESC, asking_price ASC
        LIMIT 1000
        """,
        params,
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def price_history(conn: sqlite3.Connection, listing_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT seen_date, asking_price, price_per_m2
        FROM price_history
        WHERE listing_id = ?
        ORDER BY seen_date
        """,
        (listing_id,),
    ).fetchall()
    return [row_to_dict(row) for row in rows]


def stats(conn: sqlite3.Connection) -> dict[str, Any]:
    current = conn.execute(
        """
        SELECT COUNT(*) AS active_count, AVG(price_per_m2) AS avg_price_per_m2
        FROM listings
        WHERE status = 'active'
        """
    ).fetchone()
    seven_days_ago = (date.today() - timedelta(days=7)).isoformat()
    trend = conn.execute(
        """
        SELECT event_type, COUNT(*) AS count
        FROM events
        WHERE event_date >= ?
        GROUP BY event_type
        """,
        (seven_days_ago,),
    ).fetchall()
    regions = conn.execute(
        """
        SELECT region, COUNT(*) AS count, AVG(price_per_m2) AS avg_price_per_m2
        FROM listings
        WHERE status = 'active'
        GROUP BY region
        ORDER BY count DESC
        """
    ).fetchall()
    last_run = conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT 1").fetchone()

    return {
        "active_count": current["active_count"] or 0,
        "avg_price_per_m2": round(current["avg_price_per_m2"] or 0),
        "seven_day_trend": [row_to_dict(row) for row in trend],
        "regions": [row_to_dict(row) for row in regions],
        "last_run": row_to_dict(last_run) if last_run else None,
    }
