#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
AREA_PATH = REPO / "data" / "area_research.json"
BACKUP_DIR = REPO / "data" / "backups"
VALIDATOR = REPO / "scripts" / "validate_area_research_proposal.py"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def shallow_merge_profile(profile: dict[str, Any], changes: dict[str, Any]) -> dict[str, Any]:
    merged = dict(profile)
    for key, value in changes.items():
        if key == "id":
            continue
        merged[key] = value
    return merged


def validate(proposal: Path) -> None:
    subprocess.run([str(VALIDATOR), str(proposal)], cwd=REPO, check=True)


def build_updated_profiles(proposal: dict[str, Any], existing: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    messages: list[str] = []
    by_id = {str(profile.get("id")): idx for idx, profile in enumerate(existing)}
    updated = list(existing)

    for addition in proposal.get("proposed_profile_additions", []):
        addition_id = str(addition.get("id"))
        if addition_id in by_id:
            messages.append(f"SKIP addition {addition_id}: id already exists")
            continue
        by_id[addition_id] = len(updated)
        updated.append(addition)
        messages.append(f"ADD {addition_id}: {addition.get('name')}")

    for change in proposal.get("proposed_profile_updates", []):
        profile_id = str(change.get("id"))
        idx = by_id.get(profile_id)
        if idx is None:
            messages.append(f"SKIP update {profile_id}: no existing profile with that id")
            continue
        suggested = change.get("suggested_changes") or {}
        updated[idx] = shallow_merge_profile(updated[idx], suggested)
        messages.append(f"UPDATE {profile_id}: {', '.join(sorted(suggested))}")

    return updated, messages


def main() -> int:
    parser = argparse.ArgumentParser(description="Review/apply a non-destructive area research proposal.")
    parser.add_argument("--proposal", required=True, type=Path, help="Path to proposal JSON")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dry-run", action="store_true", help="Preview changes only (default)")
    group.add_argument("--apply", action="store_true", help="Apply proposal to data/area_research.json with backup")
    args = parser.parse_args()

    proposal_path = args.proposal if args.proposal.is_absolute() else REPO / args.proposal
    validate(proposal_path)
    proposal = load_json(proposal_path)
    existing = load_json(AREA_PATH)
    if not isinstance(existing, list):
        raise SystemExit(f"{AREA_PATH} must be a JSON list")

    updated, messages = build_updated_profiles(proposal, existing)
    print("Proposal:", proposal_path)
    print("Current profiles:", len(existing))
    print("Profiles after proposal:", len(updated))
    print("Planned actions:")
    for message in messages:
        print("-", message)

    if not args.apply:
        print("\nDRY RUN ONLY. Nothing was changed. Re-run with --apply after explicit approval.")
        return 0

    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BACKUP_DIR / f"area_research_{stamp}.json"
    shutil.copy2(AREA_PATH, backup)
    write_json(AREA_PATH, updated)
    print(f"\nAPPLIED. Backup created: {backup}")
    print("Recommended next step: .venv/bin/python -m pytest")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
