from __future__ import annotations

import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent
sys.path.insert(0, str(project_root / ".vendor_local"))

from flask import Flask, jsonify, redirect, render_template, request

import area_research
import database
import preferences
import recommendations
import scraper


app = Flask(__name__)


def get_db():
    conn = database.connect()
    database.init_db(conn)
    return conn


@app.get("/")
def index():
    return render_template("index.html")


@app.get("/today")
def today():
    return render_template("today.html")


@app.get("/api/listings")
def api_listings():
    filters = {
        "region": request.args.get("region"),
        "energy_rating": request.args.get("energy_rating"),
        "price_min": request.args.get("price_min", type=int),
        "price_max": request.args.get("price_max", type=int),
        "size_min": request.args.get("size_min", type=float),
        "size_max": request.args.get("size_max", type=float),
        "rooms_min": request.args.get("rooms_min", type=float),
        "rooms_max": request.args.get("rooms_max", type=float),
        "ppm_min": request.args.get("ppm_min", type=int),
        "ppm_max": request.args.get("ppm_max", type=int),
        "days_on_market_max": request.args.get("days_on_market_max", type=int),
        "lot_size_min": request.args.get("lot_size_min", type=float),
        "has_image": request.args.get("has_image") in {"1", "true", "True", "yes"},
    }
    with get_db() as conn:
        return jsonify(database.list_active(conn, filters))


@app.get("/api/listings/<listing_id>/history")
def api_history(listing_id: str):
    with get_db() as conn:
        return jsonify(database.price_history(conn, listing_id))


@app.get("/api/stats")
def api_stats():
    with get_db() as conn:
        return jsonify(database.stats(conn))


@app.get("/api/preferences")
def api_get_preferences():
    return jsonify(preferences.load_preferences())


@app.get("/api/area-research")
def api_area_research():
    return jsonify(area_research.public_profiles())


@app.put("/api/preferences")
def api_put_preferences():
    payload = request.get_json(silent=True) or {}
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "error": "Preferences payload must be a JSON object"}), 400
    return jsonify(preferences.save_preferences(payload))


@app.get("/api/recommendations")
def api_recommendations():
    with get_db() as conn:
        return jsonify(recommendations.latest_categories(conn))


@app.get("/api/public/today")
def api_public_today():
    selected_date = request.args.get("date")
    with get_db() as conn:
        return jsonify(recommendations.public_daily_for_date(conn, selected_date))


@app.post("/api/recommendations/generate")
def api_generate_recommendations():
    with get_db() as conn:
        result = recommendations.generate(conn)
        return jsonify(
            {
                "ok": True,
                "run_id": result["run_id"],
                "item_count": result["item_count"],
                "counts": {
                    category: len(items)
                    for category, items in result["categories"].items()
                },
            }
        )


@app.get("/api/agent/daily")
def api_agent_daily():
    with get_db() as conn:
        return jsonify(recommendations.items_for_category(conn, "daily"))


@app.get("/api/agent/weekly")
def api_agent_weekly():
    with get_db() as conn:
        return jsonify(recommendations.items_for_category(conn, "weekly"))


@app.get("/api/agent/price-drops")
def api_agent_price_drops():
    with get_db() as conn:
        return jsonify(recommendations.items_for_category(conn, "price_drops"))


@app.get("/api/agent/hidden-gems")
def api_agent_hidden_gems():
    with get_db() as conn:
        return jsonify(recommendations.items_for_category(conn, "hidden_gems"))


@app.get("/api/agent/ai-highlights")
def api_agent_ai_highlights():
    with get_db() as conn:
        return jsonify(recommendations.items_for_category(conn, "ai_highlights"))


@app.get("/api/agent/open-houses")
def api_agent_open_houses():
    with get_db() as conn:
        return jsonify(recommendations.items_for_category(conn, "open_houses"))


@app.get("/api/listings/<listing_id>/analysis")
def api_listing_analysis(listing_id: str):
    with get_db() as conn:
        item = recommendations.listing_analysis(conn, listing_id)
        if item is None:
            return jsonify({"ok": False, "error": "Listing not found"}), 404
        return jsonify(item)


@app.get("/api/listings/<listing_id>/broker-redirect")
def api_listing_broker_redirect(listing_id: str):
    with get_db() as conn:
        row = conn.execute(
            "SELECT listing_url, raw_json FROM listings WHERE listing_id = ?",
            (listing_id,),
        ).fetchone()
        if row is None:
            return jsonify({"ok": False, "error": "Listing not found"}), 404

        raw = recommendations.raw_for(dict(row))
        target = scraper.broker_url(raw)
        if target is None:
            try:
                target = scraper.fetch_broker_url(listing_id)
            except Exception:
                target = None
        target = target or row["listing_url"]
        if not target:
            return jsonify({"ok": False, "error": "No external URL found"}), 404
        return redirect(target, code=302)


@app.post("/api/listings/<listing_id>/feedback")
def api_listing_feedback(listing_id: str):
    payload = request.get_json(silent=True) or {}
    feedback_type = payload.get("feedback_type")
    if not feedback_type:
        return jsonify({"ok": False, "error": "feedback_type is required"}), 400
    with get_db() as conn:
        try:
            result = recommendations.add_feedback(conn, listing_id, feedback_type, payload.get("note"))
        except ValueError as exc:
            return jsonify({"ok": False, "error": str(exc)}), 400
        return jsonify({"ok": True, **result})


@app.post("/api/listings/<listing_id>/watch")
def api_listing_watch(listing_id: str):
    payload = request.get_json(silent=True) or {}
    with get_db() as conn:
        return jsonify(recommendations.set_watch(conn, listing_id, payload.get("note")))


@app.delete("/api/listings/<listing_id>/watch")
def api_listing_unwatch(listing_id: str):
    with get_db() as conn:
        return jsonify(recommendations.delete_watch(conn, listing_id))


@app.get("/api/watchlist")
def api_watchlist():
    with get_db() as conn:
        return jsonify(recommendations.watchlist(conn))


@app.get("/api/map/listings")
def api_map_listings():
    limit = request.args.get("limit", default=10000, type=int)
    limit = max(1, min(limit, 10000))
    with get_db() as conn:
        return jsonify(recommendations.map_listings(conn, limit=limit))


@app.post("/api/scrape")
def api_scrape():
    max_pages = request.args.get("max_pages", type=int)
    with get_db() as conn:
        run_id = database.start_run(conn)
        try:
            result = scraper.fetch_all(max_pages=max_pages)
            counts = database.sync_listings(conn, result.listings, run_id)
            database.finish_run(conn, run_id, "ok", "Scrape completed", len(result.listings))
            return jsonify({"ok": True, "fetched": len(result.listings), "counts": counts})
        except scraper.BoligaBlockedError as exc:
            database.finish_run(conn, run_id, "blocked", str(exc), 0)
            return jsonify({"ok": False, "error": str(exc)}), 502
        except Exception as exc:
            database.finish_run(conn, run_id, "error", str(exc), 0)
            return jsonify({"ok": False, "error": str(exc)}), 500


if __name__ == "__main__":
    with get_db():
        pass
    # Bind defaults stay safe for local/tunnel use, but can be overridden for Docker.
    # Example: SUMMERHOUSE_HOST=0.0.0.0 SUMMERHOUSE_PORT=8080 python app.py
    import os

    host = os.getenv("SUMMERHOUSE_HOST", "127.0.0.1")
    port = int(os.getenv("SUMMERHOUSE_PORT", "8080"))
    app.run(host=host, port=port, debug=False)
