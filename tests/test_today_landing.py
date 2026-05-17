from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_today_landing_page_route_and_assets_exist() -> None:
    app_source = (ROOT / "app.py").read_text()
    today_html = (ROOT / "templates" / "today.html").read_text()
    today_js = (ROOT / "static" / "today.js").read_text()
    index_html = (ROOT / "templates" / "index.html").read_text()

    assert '@app.get("/today")' in app_source
    assert 'Dagens top 5' in today_html
    assert '/static/today.js' in today_html
    assert 'href="/today"' in index_html
    assert '/api/agent/daily' in today_js
    assert '.slice(0, 5)' in today_js


def test_today_landing_page_has_no_dashboard_filters_or_map() -> None:
    today_html = (ROOT / "templates" / "today.html").read_text()
    today_js = (ROOT / "static" / "today.js").read_text()

    assert 'data-view="map"' not in today_html
    assert 'data-view="preferences"' not in today_html
    assert 'filterPanel' not in today_js
    assert 'renderMap' not in today_js
