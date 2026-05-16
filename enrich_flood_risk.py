from __future__ import annotations

import argparse

import database
import flood_risk


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich listings with geo risk indicators: low elevation, KAMP storm surge, and DinGeo historical-flood links.")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()

    with database.connect() as conn:
        database.init_db(conn)
        rows = conn.execute(
            """
            SELECT l.*
            FROM listings l
            LEFT JOIN listing_scores s ON s.listing_id = l.listing_id
            WHERE l.status = 'active' AND l.latitude IS NOT NULL AND l.longitude IS NOT NULL
            ORDER BY COALESCE(s.fit_score, 0) DESC, l.asking_price ASC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        for row in rows:
            listing = database.row_to_dict(row)
            warning = flood_risk.upsert_assessment(conn, listing)
            print(f"{listing['listing_id']}: {warning['warning_level']} - {warning['warning_text'][:100]}")
        conn.commit()
    print(f"Checked {len(rows)} listings for geo risk: terrain elevation, KAMP storm-surge coastal references, and DinGeo historical-flood links.")


if __name__ == "__main__":
    main()
