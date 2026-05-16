# Area research agent workflow

This project uses a deliberately non-destructive research workflow.

## Weekly research job

The scheduled research agent should:

1. Read the current `data/area_research.json` profiles.
2. Research Sjælland and bridge-connected island summerhouse areas relevant to Jeppee's criteria.
3. Produce a new proposal JSON file in `data/research_proposals/`.
4. Validate the proposal with `scripts/validate_area_research_proposal.py`.
5. Send a concise Telegram summary with the proposal path and recommended next action.

The job must not directly change production area data or dashboard code.

## Proposal file shape

Each proposal is a JSON object:

```json
{
  "schema_version": 1,
  "non_destructive": true,
  "generated_at": "2026-05-16T14:00:00Z",
  "summary_da": "Kort dansk opsummering",
  "research_focus": ["hidden gems", "transport", "flood caveats"],
  "proposed_profile_additions": [
    {
      "id": "slug",
      "name": "Area name",
      "region": "Region",
      "language": "da",
      "access_scope": "sjælland_bridge_connected",
      "postal_ranges": [[4500, 4500]],
      "match_terms": ["Area"],
      "area_fit_score": 80,
      "hidden_gem_score": 75,
      "vibe": "Short factual/interpretive vibe",
      "opinionated_take": "Agent opinion, clearly opinionated",
      "best_for": ["Value"],
      "watch_outs": ["Flood risk should be checked"],
      "transport_note": "Car/public transport caveat",
      "service_note": "Nearby services caveat",
      "sources": [{"title": "Source", "url": "https://example.com"}]
    }
  ],
  "proposed_profile_updates": [
    {
      "id": "existing-area-id",
      "rationale_da": "Why update this profile",
      "suggested_changes": {
        "watch_outs": ["Additional caveat"],
        "sources": [{"title": "New source", "url": "https://example.com"}]
      },
      "sources": [{"title": "Evidence", "url": "https://example.com"}]
    }
  ],
  "areas_considered_but_rejected": [
    {
      "name": "Area",
      "reason_da": "Why it is not a good fit right now",
      "sources": [{"title": "Source", "url": "https://example.com"}]
    }
  ],
  "manual_review_checklist_da": ["Tjek transporttid", "Tjek flood/lavbund"]
}
```

## Applying proposals

Dry-run first:

```bash
cd /opt/data/repos/summerhouse-agent
.venv/bin/python scripts/apply_area_research_proposal.py --proposal data/research_proposals/YYYY-MM-DD_area_research_proposal.json --dry-run
```

Apply only after explicit approval:

```bash
cd /opt/data/repos/summerhouse-agent
.venv/bin/python scripts/apply_area_research_proposal.py --proposal data/research_proposals/YYYY-MM-DD_area_research_proposal.json --apply
.venv/bin/python -m pytest
```

The apply script creates a timestamped backup in `data/backups/` before writing `data/area_research.json`.
