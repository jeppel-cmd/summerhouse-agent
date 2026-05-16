from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import app as app_module
import database
import scraper


def make_db(tmp_path: Path, raw: dict | None = None, listing_url: str = "https://www.boliga.dk/adresse/test"):
    db_path = tmp_path / "test.sqlite"
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    database.init_db(conn)
    conn.execute(
        """
        INSERT INTO listings (
            listing_id, address, city, listing_url, first_seen_date, last_seen_date, status, raw_json
        ) VALUES (?, ?, ?, ?, ?, ?, 'active', ?)
        """,
        (
            "test-1",
            "Testvej 1",
            "Testby",
            listing_url,
            "2026-01-01",
            "2026-01-01",
            json.dumps(raw or {}, ensure_ascii=False),
        ),
    )
    conn.commit()
    conn.close()

    def get_db():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        return conn

    return get_db


def test_broker_redirect_prefers_broker_url_from_raw_json(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        app_module,
        "get_db",
        make_db(tmp_path, {"estateUrl": "https://maegler.example/listing"}),
    )

    response = app_module.app.test_client().get("/api/listings/test-1/broker-redirect")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://maegler.example/listing"


def test_broker_redirect_fetches_detail_url_and_falls_back_to_boliga(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app_module, "get_db", make_db(tmp_path))
    monkeypatch.setattr(scraper, "fetch_broker_url", lambda listing_id: "https://detail-maegler.example/listing")

    response = app_module.app.test_client().get("/api/listings/test-1/broker-redirect")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://detail-maegler.example/listing"


def test_broker_redirect_falls_back_to_boliga_when_detail_fetch_fails(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(app_module, "get_db", make_db(tmp_path))

    def fail(_listing_id: str) -> str | None:
        raise scraper.BoligaBlockedError("blocked")

    monkeypatch.setattr(scraper, "fetch_broker_url", fail)

    response = app_module.app.test_client().get("/api/listings/test-1/broker-redirect")

    assert response.status_code == 302
    assert response.headers["Location"] == "https://www.boliga.dk/adresse/test"
