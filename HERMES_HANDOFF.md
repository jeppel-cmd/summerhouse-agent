# Hermes Handoff

This is Jeppe's local Sommerhus Agent.

## Product Direction

The goal is a personal summerhouse agent for finding interesting Danish holiday homes, mostly on Zealand.

Good listings fit most of the criteria, not just the lowest price:

- Zealand / Greater Copenhagen / practical travel from Copenhagen Central.
- Near water, nature, quiet, privacy.
- Good for family use.
- Some rental potential.
- Fair value for the area.
- Renovation projects are fine when priced appropriately.
- Seller motivation and price drops are useful, but should not dominate.
- Flood risk should be shown as a warning, not used as a hard score killer.

## Current Implementation

Backend:

- Flask in `app.py`.
- SQLite in `database.py`.
- Boliga JSON scraper in `scraper.py`.
- Preferences in `preferences.json` via `preferences.py`.
- Recommendation scoring in `recommendations.py`.
- Flood-risk interface stub in `flood_risk.py`.

Frontend:

- `templates/index.html`
- `static/app.js`
- `static/style.css`

Current UI sections:

- `Match`: recommendation cards with live filters.
- `Kort`: graphical Zealand map split into Nord, Øst, Vest, Syd.
- `Favoritter`: watchlist.
- `Præferencer`: editable preferences and free-text AI-highlight description.

## API Shape

Important endpoints:

- `GET/PUT /api/preferences`
- `GET /api/recommendations`
- `POST /api/recommendations/generate`
- `GET /api/agent/daily`
- `GET /api/agent/weekly`
- `GET /api/agent/price-drops`
- `GET /api/agent/hidden-gems`
- `GET /api/agent/open-houses`
- `GET /api/agent/ai-highlights`
- `GET /api/map/listings`
- `GET /api/listings/<id>/analysis`
- `POST /api/listings/<id>/feedback`
- `POST /api/listings/<id>/watch`
- `DELETE /api/listings/<id>/watch`
- `GET /api/watchlist`

## Important Guardrails

- Do not parse Boliga HTML. Use the JSON endpoint documented in `boliga_research.md`.
- Do not commit `data/boliga.sqlite`.
- Do not introduce heavy frameworks unless Jeppe explicitly asks.
- Keep backend local-first and SQLite-based.
- Keep `preferences.json` human-editable.
- Do not hardcode a max price. Let preferences and UI filters control that.
- Keep feedback simple: `favorite`, `like`, `dislike`.

## Known Improvement Areas

- Replace travel proxy with real public transport and car routing later.
- Add official Danish flood-risk enrichment from KAMP / HIP / Dataforsyningen.
- Improve area mapping beyond postal-prefix buckets.
- Make AI highlights use an LLM later; currently this is deterministic text matching/scoring.
- Add tests around scoring and recommendation categories.

## Run Commands

```powershell
python app.py
python generate_recommendations.py
python -m py_compile app.py database.py scraper.py preferences.py recommendations.py flood_risk.py generate_recommendations.py
node --check static\app.js
```
