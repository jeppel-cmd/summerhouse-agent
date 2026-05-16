# Summerhouse Agent project rules

## Non-destructive area research workflow

The summerhouse project has an opinionated area-intelligence layer in `data/area_research.json`.

Scheduled/background research agents MUST be non-destructive:

- Do NOT edit `data/area_research.json` directly.
- Do NOT rewrite `preferences.json`, scoring code, dashboard code, or database contents as part of research-only work.
- Do NOT run `git add`, `git commit`, or `git push` from the research agent.
- Write proposed research to `data/research_proposals/` as a new dated proposal file instead.
- Include Danish source links, caveats, and a clear separation between facts and agent opinion.
- Run `scripts/validate_area_research_proposal.py <proposal.json>` before reporting success.

Only apply proposal data to `data/area_research.json` after an explicit user request to review/apply a specific proposal. Use `scripts/apply_area_research_proposal.py --proposal <file> --dry-run` first, then `--apply` only after the user agrees. The apply script creates a timestamped backup under `data/backups/`.
