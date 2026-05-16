from __future__ import annotations

from datetime import datetime
from typing import Any


SOURCE_NAME = "pending_official_danish_enrichment"


def placeholder_warning(listing: dict[str, Any]) -> dict[str, Any]:
    """Return the flood-risk shape before official KAMP/HIP data is wired in."""
    return {
        "listing_id": listing["listing_id"],
        "warning_level": "unknown",
        "warning_text": "Oversvømmelsesrisiko er endnu ikke tjekket mod officielle danske data.",
        "source": SOURCE_NAME,
        "trigger_json": {},
        "last_checked_at": datetime.now().isoformat(timespec="seconds"),
    }


def upsert_placeholder(conn, listing: dict[str, Any]) -> dict[str, Any]:
    warning = placeholder_warning(listing)
    conn.execute(
        """
        INSERT INTO flood_risk (
            listing_id, warning_level, warning_text, source, trigger_json, last_checked_at
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(listing_id) DO UPDATE SET
            warning_level = excluded.warning_level,
            warning_text = excluded.warning_text,
            source = excluded.source,
            trigger_json = excluded.trigger_json,
            last_checked_at = excluded.last_checked_at
        """,
        (
            warning["listing_id"],
            warning["warning_level"],
            warning["warning_text"],
            warning["source"],
            "{}",
            warning["last_checked_at"],
        ),
    )
    return warning
