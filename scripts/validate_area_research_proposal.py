#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.parse import urlparse

REQUIRED_PROFILE_FIELDS = {
    "id",
    "name",
    "region",
    "language",
    "access_scope",
    "postal_ranges",
    "match_terms",
    "area_fit_score",
    "hidden_gem_score",
    "vibe",
    "opinionated_take",
    "best_for",
    "watch_outs",
    "transport_note",
    "service_note",
    "sources",
}


def fail(message: str) -> None:
    raise SystemExit(f"INVALID: {message}")


def load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        fail(f"{path} is not valid JSON: {exc}")
    if not isinstance(data, dict):
        fail("proposal root must be a JSON object")
    return data


def validate_sources(sources: object, context: str) -> None:
    if not isinstance(sources, list) or not sources:
        fail(f"{context}.sources must be a non-empty list")
    for idx, source in enumerate(sources, 1):
        if not isinstance(source, dict):
            fail(f"{context}.sources[{idx}] must be an object")
        title = str(source.get("title") or "").strip()
        url = str(source.get("url") or "").strip()
        if not title:
            fail(f"{context}.sources[{idx}] missing title")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            fail(f"{context}.sources[{idx}] has invalid URL: {url!r}")


def validate_profile(profile: object, context: str) -> None:
    if not isinstance(profile, dict):
        fail(f"{context} must be an object")
    missing = sorted(REQUIRED_PROFILE_FIELDS - set(profile))
    if missing:
        fail(f"{context} missing required fields: {', '.join(missing)}")
    if profile.get("language") != "da":
        fail(f"{context}.language must be 'da'")
    for key in ("id", "name", "region", "vibe", "opinionated_take"):
        if not str(profile.get(key) or "").strip():
            fail(f"{context}.{key} must be non-empty")
    for key in ("area_fit_score", "hidden_gem_score"):
        try:
            value = int(profile[key])
        except (TypeError, ValueError):
            fail(f"{context}.{key} must be an integer")
        if not 0 <= value <= 100:
            fail(f"{context}.{key} must be between 0 and 100")
    for key in ("match_terms", "best_for", "watch_outs"):
        if not isinstance(profile.get(key), list) or not profile[key]:
            fail(f"{context}.{key} must be a non-empty list")
    ranges = profile.get("postal_ranges")
    if not isinstance(ranges, list) or not ranges:
        fail(f"{context}.postal_ranges must be a non-empty list")
    for idx, item in enumerate(ranges, 1):
        if not (isinstance(item, list) and len(item) == 2):
            fail(f"{context}.postal_ranges[{idx}] must be [start, end]")
        try:
            start, end = int(item[0]), int(item[1])
        except (TypeError, ValueError):
            fail(f"{context}.postal_ranges[{idx}] must contain integers")
        if start > end:
            fail(f"{context}.postal_ranges[{idx}] start must be <= end")
    validate_sources(profile.get("sources"), context)


def validate_update(update: object, context: str) -> None:
    if not isinstance(update, dict):
        fail(f"{context} must be an object")
    if not str(update.get("id") or "").strip():
        fail(f"{context}.id must be non-empty")
    if not str(update.get("rationale_da") or "").strip():
        fail(f"{context}.rationale_da must be non-empty")
    changes = update.get("suggested_changes")
    if not isinstance(changes, dict) or not changes:
        fail(f"{context}.suggested_changes must be a non-empty object")
    if "sources" in changes:
        validate_sources(changes["sources"], f"{context}.suggested_changes")
    validate_sources(update.get("sources"), context)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: validate_area_research_proposal.py <proposal.json>", file=sys.stderr)
        return 2
    path = Path(argv[1])
    data = load_json(path)
    if data.get("schema_version") != 1:
        fail("schema_version must be 1")
    if data.get("non_destructive") is not True:
        fail("non_destructive must be true")
    if not str(data.get("summary_da") or "").strip():
        fail("summary_da must be non-empty")

    additions = data.get("proposed_profile_additions", [])
    updates = data.get("proposed_profile_updates", [])
    rejected = data.get("areas_considered_but_rejected", [])
    if not isinstance(additions, list):
        fail("proposed_profile_additions must be a list")
    if not isinstance(updates, list):
        fail("proposed_profile_updates must be a list")
    if not additions and not updates and not rejected:
        fail("proposal must contain additions, updates, or rejected areas")
    for idx, profile in enumerate(additions, 1):
        validate_profile(profile, f"proposed_profile_additions[{idx}]")
    for idx, update in enumerate(updates, 1):
        validate_update(update, f"proposed_profile_updates[{idx}]")
    if not isinstance(rejected, list):
        fail("areas_considered_but_rejected must be a list")
    for idx, item in enumerate(rejected, 1):
        if not isinstance(item, dict):
            fail(f"areas_considered_but_rejected[{idx}] must be an object")
        if not str(item.get("name") or "").strip():
            fail(f"areas_considered_but_rejected[{idx}].name must be non-empty")
        if not str(item.get("reason_da") or "").strip():
            fail(f"areas_considered_but_rejected[{idx}].reason_da must be non-empty")
        validate_sources(item.get("sources"), f"areas_considered_but_rejected[{idx}]")
    print(f"VALID: {path}")
    print(f"Additions: {len(additions)} · Updates: {len(updates)} · Rejected: {len(rejected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
