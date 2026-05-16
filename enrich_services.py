from __future__ import annotations

import argparse
import json
import time

import database
import service_access


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich listings with nearest supermarket/service data from OpenStreetMap.")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--only-missing", action="store_true")
    args = parser.parse_args()

    with database.connect() as conn:
        database.init_db(conn)
        rows = conn.execute(
            """
            SELECT l.listing_id, l.latitude, l.longitude, l.raw_json
            FROM listings l
            LEFT JOIN listing_scores s ON s.listing_id = l.listing_id
            WHERE l.status = 'active' AND l.latitude IS NOT NULL AND l.longitude IS NOT NULL
            ORDER BY COALESCE(s.fit_score, 0) DESC, l.asking_price ASC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()
        updated = 0
        skipped = 0
        for row in rows:
            raw = json.loads(row["raw_json"] or "{}")
            if args.only_missing and isinstance(raw.get("service_access"), dict):
                skipped += 1
                continue
            enriched = service_access.enrich_listing_raw(raw, float(row["latitude"]), float(row["longitude"]))
            conn.execute(
                "UPDATE listings SET raw_json = ? WHERE listing_id = ?",
                (json.dumps(enriched, ensure_ascii=False), row["listing_id"]),
            )
            updated += 1
            service = enriched.get("service_access") or {}
            print(f"{row['listing_id']}: {service.get('nearest_name')} {service.get('estimated_car_minutes')} min")
            time.sleep(1.1)
        conn.commit()
    print(f"Updated {updated}, skipped {skipped} listings.")


if __name__ == "__main__":
    main()
