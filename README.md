# Sommerhus Agent

Local Flask app for finding interesting Danish summerhouses from Boliga data.

The app is intentionally simple: Python scraper, SQLite storage, deterministic recommendations, and a plain browser UI.

## Quick Start

```powershell
cd "C:\Users\Jeppe\Documents\Codex\Summerhouse tool"
python app.py
```

Open `http://localhost:8080`.

If you want to generate recommendation snapshots from the current SQLite data:

```powershell
python generate_recommendations.py
```

If you want to fetch fresh Boliga listings:

```powershell
python scraper.py --max-pages 1
```

You can also use the app button `Hent nye annoncer`.

## Main Files

- `app.py`: Flask app and JSON API endpoints.
- `scraper.py`: Boliga JSON API scraper. Do not scrape Boliga HTML.
- `database.py`: SQLite schema and sync logic.
- `recommendations.py`: deterministic scoring and recommendation generation.
- `preferences.py`: reads and writes `preferences.json`.
- `flood_risk.py`: stub for future official flood-risk enrichment.
- `templates/index.html`: app shell.
- `static/app.js`: frontend behavior.
- `static/style.css`: frontend styling.
- `boliga_research.md`: Boliga endpoint notes.

## Local Data

The SQLite database lives in `data/boliga.sqlite` and is intentionally ignored by git.

Tables include:

- `runs`
- `listings`
- `price_history`
- `events`
- `listing_scores`
- `recommendation_runs`
- `recommendation_items`
- `feedback`
- `watchlist`
- `flood_risk`

## Current UX

The UI is centered around:

- `Match`: best current houses with live filters.
- `Kort`: simple graphical Zealand map split into Nord, Øst, Vest, Syd.
- `Favoritter`: watched listings.
- `Præferencer`: editable preferences and AI highlight description.

The map selection updates matches directly. Match filters include price, size, rooms, score, travel proxy, images, motivated seller, hidden gems, price drops, and text search.

## Verification

```powershell
python -m py_compile app.py database.py scraper.py preferences.py recommendations.py flood_risk.py generate_recommendations.py
node --check static\app.js
```

## Notes for Future Agents

- Keep this local and beginner-friendly.
- Do not remove user data.
- Do not hardcode a price range.
- Scraping should continue to use Boliga's JSON API, not HTML parsing.
- Travel time is currently a proxy from Copenhagen Central, not a real routing integration.
- Flood risk is a warning/enrichment path, not a score killer.
