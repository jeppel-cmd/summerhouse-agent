from __future__ import annotations

import argparse

import database
import recommendations


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate stored summerhouse recommendations.")
    parser.add_argument(
        "--run-type",
        default="agent",
        help="Label for the recommendation run, such as agent, daily, or weekly.",
    )
    args = parser.parse_args()

    with database.connect() as conn:
        database.init_db(conn)
        result = recommendations.generate(conn, run_type=args.run_type)

    print(f"Recommendation run {result['run_id']} generated {result['item_count']} items.")
    for category, items in result["categories"].items():
        print(f"{category}: {len(items)}")


if __name__ == "__main__":
    main()
