from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_JS = ROOT / "static" / "app.js"


def run_node(source: str) -> str:
    completed = subprocess.run(
        ["node", "-e", source],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert completed.returncode == 0, completed.stderr
    return completed.stdout


def test_city_search_filters_full_daily_dataset_before_display_limit() -> None:
    script = APP_JS.read_text().split("\ninit().catch", 1)[0]
    listings = [
        {"listing_id": str(i), "address": f"Testvej {i}", "city": "Other", "fit_score": 1000 - i}
        for i in range(300)
    ]
    listings[-1]["city"] = "Rørvig"
    listings[-1]["fit_score"] = 1

    node_source = f"""
    const listings = {listings!r};
    global.fetch = async () => ({{ ok: true, json: async () => listings }});
    global.document = {{ createElement: () => ({{ textContent: '', get innerHTML() {{ return this.textContent; }} }}) }};
    {script}
    (async () => {{
      matchFilters.text = 'Rørvig';
      const items = await itemsForSignal('daily');
      const filtered = applyMatchFilters(items);
      if (filtered.length !== 1 || filtered[0].city !== 'Rørvig') {{
        throw new Error(`Expected city search to find Rørvig in full daily dataset, got ${{filtered.length}} result(s)`);
      }}
      console.log('ok');
    }})().catch((error) => {{ console.error(error.stack || error.message); process.exit(1); }});
    """
    assert run_node(node_source).strip() == "ok"


def test_text_filter_input_updates_results_without_rerendering_filter_panel() -> None:
    source = APP_JS.read_text()
    assert "scheduleMatchResultsRender" in source
    input_handler = source[source.index('input.addEventListener("input"'):source.index("});\n  });", source.index('input.addEventListener("input"'))]
    assert "renderMatch();" not in input_handler
    assert "scheduleMatchResultsRender" in input_handler


def test_map_area_assignments_follow_common_zealand_regions() -> None:
    script = APP_JS.read_text().split("\ninit().catch", 1)[0]
    node_source = f"""
    global.document = {{ createElement: () => ({{ textContent: '', get innerHTML() {{ return this.textContent; }} }}) }};
    {script}
    const cases = [
      [3100, 'north'], // Hornbæk / north coast
      [3210, 'north'], // Vejby / Tisvildeleje
      [4000, 'east'],  // Roskilde
      [4600, 'east'],  // Køge
      [4500, 'west'],  // Nykøbing Sjælland / Odsherred
      [4200, 'west'],  // Slagelse
      [4654, 'south'], // Faxe Ladeplads
      [4780, 'south'], // Stege / Møn
      [3700, null],    // Bornholm is ferry-only and not part of the Zealand map
    ];
    for (const [postal, expected] of cases) {{
      const area = areaForItem({{ postal_code: postal }});
      const actual = area ? area.id : null;
      if (actual !== expected) {{
        throw new Error(`Expected ${{postal}} to map to ${{expected}}, got ${{actual}}`);
      }}
    }}
    console.log('ok');
    """
    assert run_node(node_source).strip() == "ok"


def test_sort_items_orders_by_price_rooms_size_and_score() -> None:
    script = APP_JS.read_text().split("\ninit().catch", 1)[0]
    node_source = f"""
    global.document = {{ createElement: () => ({{ textContent: '', get innerHTML() {{ return this.textContent; }} }}) }};
    {script}
    const listings = [
      {{ listing_id: 'a', asking_price: 3000000, rooms: 3, size_m2: 75, price_per_m2: 40000, fit_score: 82 }},
      {{ listing_id: 'b', asking_price: 1900000, rooms: 5, size_m2: 110, price_per_m2: 17272, fit_score: 76 }},
      {{ listing_id: 'c', asking_price: 2400000, rooms: 4, size_m2: 90, price_per_m2: 26666, fit_score: 91 }},
    ];
    const ids = (key) => sortItems(listings, key).map((item) => item.listing_id).join('');
    if (ids('price_asc') !== 'bca') throw new Error(`price_asc failed: ${{ids('price_asc')}}`);
    if (ids('rooms_desc') !== 'bca') throw new Error(`rooms_desc failed: ${{ids('rooms_desc')}}`);
    if (ids('size_desc') !== 'bca') throw new Error(`size_desc failed: ${{ids('size_desc')}}`);
    if (ids('score_desc') !== 'cab') throw new Error(`score_desc failed: ${{ids('score_desc')}}`);
    console.log('ok');
    """
    assert run_node(node_source).strip() == "ok"


def test_ai_tab_is_daily_and_weekly_overview() -> None:
    source = APP_JS.read_text()
    assert 'Dagens + ugens top' in source
    assert 'renderDailyWeeklyOverview' in source


def test_area_research_tab_and_wishes_editor_exist() -> None:
    source = APP_JS.read_text()
    html = (ROOT / "templates" / "index.html").read_text()
    assert 'data-view="areas"' in html
    assert 'Områder' in html
    assert 'renderAreas' in source
    assert '/api/area-research' in source
    assert 'name="wishes_note"' in source


def test_area_cards_link_to_specific_area_listing_view() -> None:
    source = APP_JS.read_text()
    assert 'data-area-listings' in source
    assert 'renderAreaListings' in source
    assert 'Tilbage til områder' in source


def test_listing_images_link_to_broker_redirect_not_details_or_boliga() -> None:
    source = APP_JS.read_text()
    assert 'broker-redirect' in source
    assert 'aria-label="Åbn hos mægler"' in source
    assert '<a class="image-button"' in source
    assert 'href="${esc(externalUrl)}"' in source
    assert '>Boliga</a>' not in source


def test_sticky_filter_panel_is_independently_scrollable() -> None:
    css = (ROOT / "static" / "style.css").read_text()
    filter_panel_block = css[css.index(".filter-panel {"):css.index(".filter-head {")]
    assert "max-height: calc(100vh" in filter_panel_block
    assert "overflow-y: auto" in filter_panel_block

