"use strict";

const kr = new Intl.NumberFormat("da-DK");

let activeView = "match";
let activeSignal = "daily";
let watchedIds = new Set();
let selectedAreas = new Set();
let allScoredListings = [];
let currentMatchItems = [];
const signalItemsCache = new Map();
let matchRenderTimer = null;
let resultSort = "score_desc";

const matchFilters = {
  priceMin: "",
  priceMax: "",
  sizeMin: "",
  roomsMin: "",
  scoreMin: "",
  publicMax: "",
  carMax: "",
  onlyImages: false,
  onlyPriceDrops: false,
  onlyMotivated: false,
  onlyGems: false,
  text: "",
};

const signals = {
  daily: { label: "Bedste match", endpoint: "/api/map/listings?limit=10000", title: "Bedste match lige nu" },
  ai: { label: "Dagens + ugens top", endpoint: null, title: "Dagens shortlist og ugens bedste" },
  price: { label: "Prisfald", endpoint: "/api/agent/price-drops", title: "Interessante prisfald" },
  gems: { label: "Perler", endpoint: "/api/agent/hidden-gems", title: "Skjulte perler" },
  open: { label: "Fremvisninger", endpoint: "/api/agent/open-houses", title: "Kommende fremvisninger" },
};

const sortOptions = {
  score_desc: { label: "Bedste match", key: "fit_score", direction: "desc" },
  price_asc: { label: "Laveste pris", key: "asking_price", direction: "asc" },
  price_desc: { label: "Højeste pris", key: "asking_price", direction: "desc" },
  rooms_desc: { label: "Flest værelser", key: "rooms", direction: "desc" },
  size_desc: { label: "Størst m²", key: "size_m2", direction: "desc" },
  ppm_asc: { label: "Lavest kr/m²", key: "price_per_m2", direction: "asc" },
  newest: { label: "Nyeste først", key: "first_seen_date", direction: "desc" },
};

const mapAreas = [
  {
    id: "north",
    name: "Nord",
    hint: "Nordsjælland: Halsnæs, Gribskov, Helsingør, Hillerød, Frederikssund",
    postalRanges: [[3000, 3699]],
    overlayPoints: "618,170 690,118 794,76 888,84 940,142 900,242 848,330 790,365 724,316 692,232 640,214",
    labelX: 785,
    labelY: 210,
  },
  {
    id: "east",
    name: "Øst",
    hint: "Øresund og østaksen: København, Greve, Roskilde, Køge",
    postalRanges: [[2300, 2999], [4000, 4099], [4600, 4639]],
    overlayPoints: "790,365 848,330 900,242 936,382 922,506 854,612 806,682 724,674 730,568 758,466",
    labelX: 836,
    labelY: 500,
  },
  {
    id: "west",
    name: "Vest",
    hint: "Vest-/Nordvestsjælland: Odsherred, Holbæk, Kalundborg, Sorø, Slagelse",
    postalRanges: [[4100, 4599]],
    overlayPoints: "210,360 334,310 450,288 548,238 640,214 692,232 724,316 790,365 758,466 730,568 724,674 620,748 500,738 360,704 260,610 202,488",
    labelX: 500,
    labelY: 505,
  },
  {
    id: "south",
    name: "Syd",
    hint: "Sydsjælland, Stevns/Faxe samt Møn, Lolland og Falster",
    postalRanges: [[4640, 4999]],
    overlayPoints: "500,738 620,748 724,674 806,682 850,760 780,858 660,896 548,842 430,852 342,802 360,704",
    extraOverlayPoints: ["686,884 820,842 920,860 1020,926 934,990 790,972"],
    labelX: 655,
    labelY: 800,
  },
];

function fmt(value) {
  return value != null && value !== "" ? kr.format(value) : "-";
}

function esc(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

function price(value) {
  return value ? `${fmt(value)} kr.` : "-";
}

function scoreTone(score) {
  if (score >= 85) return "great";
  if (score >= 75) return "good";
  if (score >= 65) return "ok";
  return "low";
}

function formatDate(value) {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).slice(0, 20);
  return parsed.toLocaleString("da-DK", {
    weekday: "short",
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function travelLabel(item) {
  const publicMinutes = item.score_components?.estimated_public_transport_minutes;
  const carMinutes = item.score_components?.estimated_car_minutes;
  if (!publicMinutes && !carMinutes) return "-";
  return `${publicMinutes || "-"} min off. / ${carMinutes || "-"} min bil`;
}

function setStatus(message, tone = "") {
  const el = document.getElementById("globalStatus");
  el.textContent = message || "";
  el.className = `global-status ${tone}`;
}

function toast(message, tone = "ok") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast toast-${tone} visible`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.className = "toast"; }, 2400);
}

function scheduleMatchResultsRender(delayMs = 180) {
  clearTimeout(matchRenderTimer);
  matchRenderTimer = setTimeout(() => {
    renderMatchResults();
  }, delayMs);
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function postalInRanges(postal, ranges) {
  return ranges.some(([min, max]) => postal >= min && postal <= max);
}

function areaForItem(item) {
  const postal = Number(item.postal_code || 0);
  if (!postal) return null;
  return mapAreas.find((area) => postalInRanges(postal, area.postalRanges)) || null;
}

function matchesSelectedArea(item) {
  if (!selectedAreas.size) return true;
  const area = areaForItem(item);
  return area ? selectedAreas.has(area.id) : false;
}
function sortValue(item, key) {
  const value = item[key];
  if (value == null || value === "") return null;
  if (key.endsWith("_date")) {
    const time = new Date(value).getTime();
    return Number.isNaN(time) ? null : time;
  }
  return Number(value);
}

function floodLevelLabel(level) {
  return ({ high: "Høj", medium: "Mellem", watch: "Hold øje", low: "Lav", unknown: "Ukendt" })[level || "unknown"] || "Ukendt";
}

function geoRiskSummary(item) {
  const risk = item.flood_risk || {};
  const parts = [];
  if (risk.elevation_m != null) parts.push(`${risk.elevation_m} m.o.h.`);
  if (risk.low_lying_level && risk.low_lying_level !== "low") parts.push("lavt terræn");
  const historical = risk.historical_flooding;
  if (historical?.observed_flooding === true) parts.push("historisk oversvømmet");
  else if (historical?.status === "manual_check_required") parts.push("DinGeo-tjek");
  if (!parts.length && !risk.warning_level) return "";
  return `<div class="geo-risk ${esc(risk.warning_level || "unknown")}"><strong>Geo: ${esc(floodLevelLabel(risk.warning_level))}</strong><span>${esc(parts.join(" · ") || "Ikke tjekket")}</span></div>`;
}

function geoRiskDetail(item) {
  const risk = item.flood_risk || {};
  const historical = risk.historical_flooding || {};
  const detailRows = [];
  if (risk.elevation_m != null) detailRows.push(metric("Terrænhøjde", `${risk.elevation_m} m.o.h.`));
  if (risk.low_lying_level) detailRows.push(metric("Lavtliggende", floodLevelLabel(risk.low_lying_level)));
  if (risk.warning_level) detailRows.push(metric("Samlet geo-risiko", floodLevelLabel(risk.warning_level)));
  const dingeo = historical.dingeo_url ? `<p><a href="${esc(historical.dingeo_url)}" target="_blank" rel="noopener">Åbn adressen på DinGeo</a> for historiske/registrerede oversvømmelser.</p>` : "";
  return `<section><h3>Geo- og oversvømmelsesrisiko</h3>${detailRows.length ? `<div class="metrics detail-metrics">${detailRows.join("")}</div>` : ""}<p>${esc(risk.warning_text || "Ikke undersøgt endnu.")}</p>${dingeo}</section>`;
}

function sortItems(items, sortKey = resultSort) {
  const option = sortOptions[sortKey] || sortOptions.score_desc;
  const direction = option.direction === "asc" ? 1 : -1;
  return [...items].sort((a, b) => {
    const av = sortValue(a, option.key);
    const bv = sortValue(b, option.key);
    if (av == null && bv == null) return (b.fit_score || 0) - (a.fit_score || 0);
    if (av == null) return 1;
    if (bv == null) return -1;
    if (av === bv) return (b.fit_score || 0) - (a.fit_score || 0);
    return av > bv ? direction : -direction;
  });
}

function sortSelectHtml() {
  return `<label class="sort-control">Sortér <select id="resultSort">${Object.entries(sortOptions).map(([key, option]) => `<option value="${key}" ${key === resultSort ? "selected" : ""}>${esc(option.label)}</option>`).join("")}</select></label>`;
}

function attachSortListener(root) {
  root.querySelector("#resultSort")?.addEventListener("change", (event) => {
    resultSort = event.target.value;
    if (activeSignal === "ai") renderDailyWeeklyOverview();
    else renderMatchResults();
  });
}

function signalTabsHtml() {
  return `<div class="signal-tabs">${Object.entries(signals).map(([key, signal]) => `<button class="${key === activeSignal ? "active" : ""}" data-signal="${key}">${signal.label}</button>`).join("")}</div>`;
}

function attachSignalTabs(root) {
  root.querySelectorAll("[data-signal]").forEach((button) => button.addEventListener("click", () => {
    activeSignal = button.dataset.signal;
    renderMatch();
  }));
}


function metric(label, value) {
  return `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

function badges(item) {
  const out = [];
  if (item.hidden_gem) out.push("Perle");
  if (item.motivated_seller) out.push("Motiveret sælger");
  if (item.recommendation_reasons?.length) out.push("AI");
  if (item.score_components?.area_research_name) out.push(`Område: ${item.score_components.area_research_name}`);
  const oh = formatDate(item.open_house);
  if (oh) out.push(`Fremvisning ${oh}`);
  return out.map((badge) => `<span class="badge">${esc(badge)}</span>`).join("");
}

function reasons(item, limit = 3) {
  const list = (item.reasons || []).slice(0, limit);
  if (!list.length) return "";
  return `<ul class="reason-list">${list.map((reason) => `<li>${esc(reason)}</li>`).join("")}</ul>`;
}

function card(item, options = {}) {
  const id = String(item.listing_id);
  const externalUrl = `/api/listings/${encodeURIComponent(id)}/broker-redirect`;
  const imageTarget = item.image_url
    ? `<a class="image-button" href="${esc(externalUrl)}" target="_blank" rel="noopener" aria-label="Åbn hos mægler" style="background-image:url('${esc(item.image_url)}')"></a>`
    : `<button class="image-button empty" data-action="details" data-id="${esc(id)}"></button>`;
  return `<article class="listing-card${options.compact ? " compact" : ""}">
    ${imageTarget}
    <div class="card-body">
      <div class="card-head">
        <div>
          <h3>${esc(item.address || "Ukendt adresse")}</h3>
          <p>${esc([item.postal_code, item.city].filter(Boolean).join(" "))}${item.region ? ` · ${esc(item.region)}` : ""}</p>
        </div>
        <div class="score ${scoreTone(item.fit_score)}"><b>${item.fit_score != null ? Math.round(item.fit_score) : "-"}</b><span>match</span></div>
      </div>
      <div class="badge-row">${badges(item)}</div>
      <div class="metrics">
        ${metric("Pris", price(item.asking_price))}
        ${metric("Kr/m²", item.price_per_m2 ? `${fmt(item.price_per_m2)} kr.` : "-")}
        ${metric("Areal", item.size_m2 ? `${fmt(item.size_m2)} m²` : "-")}
        ${metric("Værelser", item.rooms ?? "-")}
        ${options.compact ? "" : metric("Rejse", travelLabel(item))}
      </div>
      ${options.compact ? "" : geoRiskSummary(item)}
      ${options.compact ? "" : reasons(item)}
      <div class="card-actions">
        <button data-action="favorite" data-id="${esc(id)}" class="${watchedIds.has(id) ? "active" : ""}">Favorit</button>
        <button data-action="like" data-id="${esc(id)}">Like</button>
        <button data-action="dislike" data-id="${esc(id)}" class="quiet">Dislike</button>
        <button data-action="details" data-id="${esc(id)}" class="quiet">Detaljer</button>
        ${item.listing_url ? `<a href="${esc(externalUrl)}" target="_blank" rel="noopener">Mægler</a>` : ""}
      </div>
    </div>
  </article>`;
}

function applyMatchFilters(items) {
  const numberChecks = [
    ["priceMin", "asking_price", (actual, expected) => actual >= expected],
    ["priceMax", "asking_price", (actual, expected) => actual <= expected],
    ["sizeMin", "size_m2", (actual, expected) => actual >= expected],
    ["roomsMin", "rooms", (actual, expected) => actual >= expected],
    ["scoreMin", "fit_score", (actual, expected) => actual >= expected],
  ];
  return items.filter((item) => {
    if (!matchesSelectedArea(item)) return false;
    for (const [filterKey, itemKey, test] of numberChecks) {
      const expected = Number(matchFilters[filterKey]);
      if (matchFilters[filterKey] !== "" && item[itemKey] != null && !test(Number(item[itemKey]), expected)) return false;
    }
    const publicMax = Number(matchFilters.publicMax);
    if (matchFilters.publicMax !== "" && (item.score_components?.estimated_public_transport_minutes || 9999) > publicMax) return false;
    const carMax = Number(matchFilters.carMax);
    if (matchFilters.carMax !== "" && (item.score_components?.estimated_car_minutes || 9999) > carMax) return false;
    if (matchFilters.onlyImages && !item.image_url) return false;
    if (matchFilters.onlyMotivated && !item.motivated_seller) return false;
    if (matchFilters.onlyGems && !item.hidden_gem) return false;
    if (matchFilters.onlyPriceDrops && !item.last_price_drop_date && !String(item.reasons || "").toLowerCase().includes("prisfald")) return false;
    if (matchFilters.text) {
      const haystack = `${item.address || ""} ${item.city || ""} ${item.region || ""} ${(item.reasons || []).join(" ")}`.toLowerCase();
      if (!haystack.includes(matchFilters.text.toLowerCase())) return false;
    }
    return true;
  });
}

function filterPanel(totalBefore, totalAfter) {
  const activeAreaText = selectedAreas.size
    ? [...selectedAreas].map((id) => mapAreas.find((area) => area.id === id)?.name).filter(Boolean).join(", ")
    : "Alle områder";
  return `<aside class="filter-panel">
    <div class="filter-head">
      <h3>Filtre</h3>
      <button id="clearFilters" class="quiet">Nulstil</button>
    </div>
    <div class="active-area"><span>Område</span><strong>${esc(activeAreaText)}</strong></div>
    <div class="filter-area-buttons">
      ${mapAreas.map((area) => `<button type="button" class="${selectedAreas.has(area.id) ? "active" : "quiet"}" data-filter-area="${area.id}">${esc(area.name)}</button>`).join("")}
    </div>
    <div class="filter-grid">
      <label>Min pris<input data-filter="priceMin" type="number" value="${esc(matchFilters.priceMin)}"></label>
      <label>Maks pris<input data-filter="priceMax" type="number" value="${esc(matchFilters.priceMax)}"></label>
      <label>Min m²<input data-filter="sizeMin" type="number" value="${esc(matchFilters.sizeMin)}"></label>
      <label>Min værelser<input data-filter="roomsMin" type="number" value="${esc(matchFilters.roomsMin)}"></label>
      <label>Min score<input data-filter="scoreMin" type="number" value="${esc(matchFilters.scoreMin)}"></label>
      <label>Maks off. min<input data-filter="publicMax" type="number" value="${esc(matchFilters.publicMax)}"></label>
      <label>Maks bil min<input data-filter="carMax" type="number" value="${esc(matchFilters.carMax)}"></label>
      <label>Søg tekst<input data-filter="text" value="${esc(matchFilters.text)}"></label>
    </div>
    <div class="check-row">
      <label><input data-filter="onlyImages" type="checkbox" ${matchFilters.onlyImages ? "checked" : ""}> Kun med billede</label>
      <label><input data-filter="onlyMotivated" type="checkbox" ${matchFilters.onlyMotivated ? "checked" : ""}> Motiveret sælger</label>
      <label><input data-filter="onlyGems" type="checkbox" ${matchFilters.onlyGems ? "checked" : ""}> Perler</label>
      <label><input data-filter="onlyPriceDrops" type="checkbox" ${matchFilters.onlyPriceDrops ? "checked" : ""}> Prisfald</label>
    </div>
    <p id="matchFilterSummary">${totalAfter} af ${totalBefore} huse matcher filtrene.</p>
  </aside>`;
}

function attachFilterListeners(root) {
  root.querySelectorAll("[data-filter]").forEach((input) => {
    input.addEventListener("input", () => {
      if (input.type === "checkbox") {
        matchFilters[input.dataset.filter] = input.checked;
      } else {
        matchFilters[input.dataset.filter] = input.value;
      }
      if (activeSignal === "ai") renderDailyWeeklyOverview();
      else scheduleMatchResultsRender();
    });
  });
  root.querySelector("#clearFilters")?.addEventListener("click", () => {
    Object.keys(matchFilters).forEach((key) => {
      matchFilters[key] = typeof matchFilters[key] === "boolean" ? false : "";
    });
    selectedAreas.clear();
    renderMatch();
  });
  root.querySelectorAll("[data-filter-area]").forEach((button) => {
    button.addEventListener("click", () => {
      toggleArea(button.dataset.filterArea);
    });
  });
}

function attachActions(root) {
  root.querySelectorAll("[data-action]").forEach((el) => {
    el.addEventListener("click", async (event) => {
      event.preventDefault();
      await handleAction(el.dataset.action, el.dataset.id);
    });
  });
}

async function handleAction(action, id) {
  try {
    if (action === "details") return openDetails(id);
    if (action === "favorite") {
      if (watchedIds.has(String(id))) {
        await apiFetch(`/api/listings/${id}/watch`, { method: "DELETE" });
        watchedIds.delete(String(id));
        toast("Fjernet fra favoritter");
      } else {
        await apiFetch(`/api/listings/${id}/watch`, { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
        await apiFetch(`/api/listings/${id}/feedback`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ feedback_type: "favorite" }),
        });
        watchedIds.add(String(id));
        toast("Tilføjet som favorit");
      }
      return renderActiveView();
    }
    await apiFetch(`/api/listings/${id}/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ feedback_type: action }),
    });
    toast(action === "like" ? "Markeret som interessant" : "Nedprioriteret");
  } catch (error) {
    toast(error.message, "err");
  }
}

function setView(view) {
  activeView = view;
  document.querySelectorAll(".nav-tab").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  setStatus("");
  renderActiveView();
}

async function renderActiveView() {
  if (activeView === "match") return renderMatch();
  if (activeView === "areas") return renderAreas();
  if (activeView === "map") return renderMap();
  if (activeView === "favorites") return renderFavorites();
  if (activeView === "preferences") return renderPreferences();
}

async function itemsForSignal(signalKey) {
  const config = signals[signalKey];
  if (!config.endpoint) return [];
  if (!signalItemsCache.has(signalKey)) {
    signalItemsCache.set(signalKey, apiFetch(config.endpoint));
  }
  const items = await signalItemsCache.get(signalKey);
  return signalKey === "daily"
    ? [...items].sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0))
    : items;
}

function renderMatchResults() {
  const filtered = applyMatchFilters(currentMatchItems);
  const sorted = sortItems(filtered);
  const displayItems = sorted.slice(0, 60);
  const summary = document.getElementById("matchFilterSummary");
  if (summary) summary.textContent = `${filtered.length} af ${currentMatchItems.length} huse matcher filtrene.`;
  const count = document.getElementById("matchResultCount");
  if (count) count.textContent = `${displayItems.length} vist · ${sortOptions[resultSort]?.label || "sorteret"}`;
  const body = document.getElementById("matchResultsBody");
  if (body) {
    body.innerHTML = displayItems.length
      ? `<div class="card-grid">${displayItems.map((item) => card(item)).join("")}</div>`
      : `<div class="empty">Ingen huse matcher filtrene.</div>`;
    attachActions(body);
  }
}

async function renderMatch() {
  const config = signals[activeSignal];
  if (activeSignal === "ai") return renderDailyWeeklyOverview();
  const items = await itemsForSignal(activeSignal);
  if (activeSignal === "open") return renderOpenHouseDates(items);
  currentMatchItems = items;
  const filtered = applyMatchFilters(items);
  const sorted = sortItems(filtered);
  const displayItems = sorted.slice(0, 60);
  const main = document.getElementById("appMain");
  main.innerHTML = `<section class="page-head">
    <div>
      <span class="eyebrow">Agentens shortlist</span>
      <h2>Match</h2>
      <p>Kortvalg og filtre opdaterer listen med det samme. Genberegn kun når nye data eller scoring skal opdateres.</p>
    </div>
    ${signalTabsHtml()}
  </section>
  <section class="match-layout">
    ${filterPanel(items.length, filtered.length)}
    <div class="panel">
      <div class="section-title"><h3>${esc(config.title)}</h3><span id="matchResultCount">${displayItems.length} vist · ${sortOptions[resultSort]?.label || "sorteret"}</span></div>
      <div class="result-toolbar">${sortSelectHtml()}</div>
      <div id="matchResultsBody">${displayItems.length ? `<div class="card-grid">${displayItems.map((item) => card(item)).join("")}</div>` : `<div class="empty">Ingen huse matcher filtrene.</div>`}</div>
    </div>
  </section>`;
  attachSignalTabs(main);
  attachFilterListeners(main);
  attachSortListener(main);
  attachActions(main);
}

async function renderDailyWeeklyOverview() {
  const [daily, weekly] = await Promise.all([
    apiFetch("/api/agent/daily"),
    apiFetch("/api/agent/weekly"),
  ]);
  const dailyFiltered = sortItems(applyMatchFilters(daily)).slice(0, 10);
  const weeklyFiltered = sortItems(applyMatchFilters(weekly)).slice(0, 10);
  const main = document.getElementById("appMain");
  main.innerHTML = `<section class="page-head">
    <div>
      <span class="eyebrow">Daglig og ugentlig shortlist</span>
      <h2>Dagens + ugens top</h2>
      <p>Her samler vi de huse, der er værd at kigge på i dag, sammen med ugens stærkeste kandidater. AI-begrundelserne vises stadig på kortene, når de findes.</p>
    </div>
    ${signalTabsHtml()}
  </section>
  <section class="match-layout">
    ${filterPanel(daily.length + weekly.length, dailyFiltered.length + weeklyFiltered.length)}
    <div class="daily-weekly-stack">
      <div class="panel">
        <div class="section-title"><h3>Dagens huse</h3><span>${dailyFiltered.length} vist</span></div>
        <div class="result-toolbar">${sortSelectHtml()}</div>
        ${dailyFiltered.length ? `<div class="card-grid">${dailyFiltered.map((item) => card(item)).join("")}</div>` : `<div class="empty">Ingen daglige huse matcher filtrene.</div>`}
      </div>
      <div class="panel">
        <div class="section-title"><h3>Ugens top</h3><span>${weeklyFiltered.length} vist</span></div>
        ${weeklyFiltered.length ? `<div class="card-grid">${weeklyFiltered.map((item) => card(item)).join("")}</div>` : `<div class="empty">Ingen ugentlige huse matcher filtrene.</div>`}
      </div>
    </div>
  </section>`;
  currentMatchItems = [...daily, ...weekly];
  attachSignalTabs(main);
  attachFilterListeners(main);
  attachSortListener(main);
  attachActions(main);
}

function groupOpenHouses(items) {
  const groups = new Map();
  items.filter((item) => item.open_house).forEach((item) => {
    const date = new Date(item.open_house);
    if (Number.isNaN(date.getTime())) return;
    const key = date.toISOString().slice(0, 10);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(item);
  });
  return [...groups.entries()].sort(([a], [b]) => a.localeCompare(b)).map(([key, values]) => ({
    key,
    label: new Date(`${key}T12:00:00`).toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long" }),
    items: values.sort((a, b) => String(a.open_house).localeCompare(String(b.open_house))),
  }));
}

function renderOpenHouseDates(items) {
  const main = document.getElementById("appMain");
  const filtered = applyMatchFilters(items);
  const groups = groupOpenHouses(filtered);
  const selected = groups[0]?.key || "";
  main.innerHTML = `<section class="page-head">
    <div><span class="eyebrow">Planlæg fremvisninger</span><h2>Fremvisninger</h2><p>Vælg en dato først, og se derefter kun de huse der kan fremvises den dag.</p></div>
    ${signalTabsHtml()}
  </section>
  <section class="open-layout">
    <aside class="date-list">
      <h3>Datoer</h3>
      ${groups.length ? groups.map((group, index) => `<button class="date-card ${index === 0 ? "active" : ""}" data-date="${group.key}"><strong>${esc(group.label)}</strong><span>${group.items.length} huse</span></button>`).join("") : `<div class="empty mini">Ingen kommende fremvisninger.</div>`}
    </aside>
    <div class="panel open-results"><div id="openHouseResults"></div></div>
  </section>`;
  attachSignalTabs(main);
  main.querySelectorAll("[data-date]").forEach((button) => button.addEventListener("click", () => {
    main.querySelectorAll("[data-date]").forEach((dateButton) => dateButton.classList.toggle("active", dateButton === button));
    renderOpenHouseGroup(groups, button.dataset.date);
  }));
  if (selected) renderOpenHouseGroup(groups, selected);
}

function renderOpenHouseGroup(groups, key) {
  const target = document.getElementById("openHouseResults");
  const group = groups.find((candidate) => candidate.key === key);
  if (!target || !group) return;
  target.innerHTML = `<div class="section-title"><h3>${esc(group.label)}</h3><span>${group.items.length} huse</span></div><div class="card-grid">${group.items.map((item) => card(item)).join("")}</div>`;
  attachActions(target);
}

async function renderMap() {
  allScoredListings = allScoredListings.length ? allScoredListings : await apiFetch("/api/map/listings?limit=10000");
  const counts = areaCounts(allScoredListings);
  const chosen = selectedAreas.size ? selectedAreas : new Set(mapAreas.map((area) => area.id));
  const selectedItems = allScoredListings
    .filter((item) => {
      const area = areaForItem(item);
      return area && chosen.has(area.id);
    })
    .sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0))
    .slice(0, 60);

  const main = document.getElementById("appMain");
  main.innerHTML = `<section class="page-head map-head">
    <div><span class="eyebrow">Geografisk overblik</span><h2>Kort</h2><p>Klik nord, syd, øst eller vest til/fra. Områderne følger almindelige danske betegnelser: Nordsjælland mod nordøst, Vest-/Nordvestsjælland mod vest, Østsjælland langs Øresund/Roskilde/Køge og Sydsjælland inkl. Møn/Lolland-Falster.</p></div>
    <div class="map-actions"><button id="clearAreas" class="quiet">Ryd områdevalg</button></div>
  </section>
  <section class="map-layout">
    <div class="area-map" aria-label="Klikbart områdekort baseret på brugerens kort">
      <div class="actual-map-frame">
        <img class="actual-map-image" src="/static/assets/denmark-reference-map.jpg" alt="Brugerens kort over Sjælland, Lolland-Falster og Møn">
        <svg class="actual-map-overlay" viewBox="0 0 1280 1064" role="img" aria-label="Klikbare områder på brugerens kort">
          ${mapAreas.map((area) => `<g class="region-shape ${selectedAreas.has(area.id) ? "selected" : ""}" data-area="${area.id}">
            <polygon points="${area.overlayPoints}"></polygon>
            ${(area.extraOverlayPoints || []).map((points) => `<polygon points="${points}"></polygon>`).join("")}
            <text x="${area.labelX}" y="${area.labelY}">${esc(area.name)}</text>
            <text class="area-count" x="${area.labelX}" y="${area.labelY + 30}">${counts[area.id] || 0} huse</text>
          </g>`).join("")}
        </svg>
      </div>
      <div class="area-buttons">
        ${mapAreas.map((area) => `<button class="area-chip ${selectedAreas.has(area.id) ? "active" : ""}" data-area="${area.id}"><strong>${esc(area.name)}</strong><span>${esc(area.hint)} · ${counts[area.id] || 0}</span></button>`).join("")}
      </div>
    </div>
    <aside class="map-list">
      <div class="section-title"><h3>Valgte områder</h3><span>${selectedItems.length} huse</span></div>
      <div class="visible-list">${selectedItems.map((item) => card(item, { compact: true })).join("")}</div>
    </aside>
  </section>`;
  main.querySelectorAll("[data-area]").forEach((element) => element.addEventListener("click", () => toggleArea(element.dataset.area)));
  document.getElementById("clearAreas").addEventListener("click", () => {
    selectedAreas.clear();
    renderMap();
  });
  attachActions(main);
}

function areaCounts(items) {
  const counts = {};
  items.forEach((item) => {
    const area = areaForItem(item);
    if (area) counts[area.id] = (counts[area.id] || 0) + 1;
  });
  return counts;
}

function toggleArea(areaId) {
  if (selectedAreas.has(areaId)) selectedAreas.delete(areaId);
  else selectedAreas.add(areaId);
  if (activeView === "map") renderMap();
  else renderMatch();
}

async function loadAreaContext() {
  const areas = await apiFetch("/api/area-research");
  const listings = allScoredListings.length ? allScoredListings : await apiFetch("/api/map/listings?limit=10000");
  allScoredListings = listings;
  return { areas, listings };
}

function listingsForArea(listings, areaId) {
  return listings.filter((item) => item.score_components?.area_research_id === areaId || item.components?.area_research_id === areaId);
}

function attachAreaListingLinks(root) {
  root.querySelectorAll("[data-area-listings]").forEach((button) => button.addEventListener("click", () => {
    renderAreaListings(button.dataset.areaListings);
  }));
}

async function renderAreas() {
  const { areas, listings } = await loadAreaContext();
  const countFor = (area) => listingsForArea(listings, area.id).length;
  const main = document.getElementById("appMain");
  main.innerHTML = `<section class="page-head"><div><span class="eyebrow">Agentens område-research</span><h2>Områder</h2><p>Opinionated research uden for Boliga-listen: hvor jeg synes vi bør kigge, hvor vi skal være skeptiske, og hvorfor. Klik på et område for at se de konkrete huse.</p></div></section>
  <section class="area-grid">
    ${areas.map((area) => `<article class="area-card">
      <div class="area-card-head"><div><span class="eyebrow">${esc(area.region)}</span><h3>${esc(area.name)}</h3></div><div class="score ${scoreTone(area.area_fit_score || 0)}"><b>${Math.round(area.area_fit_score || 0)}</b><span>område</span></div></div>
      <p class="area-vibe">${esc(area.vibe || "")}</p>
      <p class="area-take">${esc(area.opinionated_take || "")}</p>
      <div class="badge-row">${(area.best_for || []).map((item) => `<span class="badge">${esc(item)}</span>`).join("")}</div>
      <div class="area-notes"><p><strong>Transport:</strong> ${esc(area.transport_note || "Tjek konkret adresse.")}</p><p><strong>Service:</strong> ${esc(area.service_note || "Tjek lokale indkøbsmuligheder.")}</p></div>
      ${(area.watch_outs || []).length ? `<div class="area-watch"><strong>Vær kritisk:</strong><ul>${area.watch_outs.map((item) => `<li>${esc(item)}</li>`).join("")}</ul></div>` : ""}
      <div class="area-links">${(area.sources || []).map((source) => `<a href="${esc(source.url)}" target="_blank" rel="noopener">${esc(source.title)}</a>`).join("")}</div>
      <div class="area-footer"><span>${countFor(area)} aktuelle huse matcher området</span><button class="quiet" data-area-listings="${esc(area.id)}">Se huse</button></div>
    </article>`).join("")}
  </section>`;
  attachAreaListingLinks(main);
}

async function renderAreaListings(areaId) {
  const { areas, listings } = await loadAreaContext();
  const area = areas.find((item) => item.id === areaId);
  const items = sortItems(listingsForArea(listings, areaId)).slice(0, 120);
  const main = document.getElementById("appMain");
  main.innerHTML = `<section class="page-head"><div><span class="eyebrow">Områdehuse</span><h2>${esc(area?.name || "Område")}</h2><p>${esc(area?.opinionated_take || "Konkrete huse koblet til område-researchen.")}</p></div><button class="quiet" id="backToAreas">Tilbage til områder</button></section>
  <section class="panel">
    <div class="section-title"><h3>Konkrete huse i området</h3><span>${items.length} vist</span></div>
    ${items.length ? `<div class="card-grid">${items.map((item) => card(item)).join("")}</div>` : `<div class="empty">Ingen aktuelle huse matcher dette område endnu.</div>`}
  </section>`;
  document.getElementById("backToAreas")?.addEventListener("click", renderAreas);
  attachActions(main);
}

async function renderFavorites() {
  const items = await apiFetch("/api/watchlist");
  const main = document.getElementById("appMain");
  main.innerHTML = `<section class="page-head"><div><span class="eyebrow">Seriøse kandidater</span><h2>Favoritter</h2><p>De huse du har markeret med favorit.</p></div></section>
  <section class="panel">${items.length ? `<div class="card-grid">${items.map((item) => card(item)).join("")}</div>` : `<div class="empty">Du har ikke tilføjet favoritter endnu.</div>`}</section>`;
  attachActions(main);
}

async function renderPreferences() {
  const prefs = await apiFetch("/api/preferences");
  const filters = prefs.filters || {};
  const search = prefs.search || {};
  const main = document.getElementById("appMain");
  main.innerHTML = `<section class="page-head"><div><span class="eyebrow">Hvad leder vi efter?</span><h2>Ønsker</h2><p>Skriv det menneskelige brief her. Agenten bruger det som sommerhusets MEMORY.md, mens tallene nedenfor stadig fungerer som konkrete pejlemærker.</p></div></section>
  <section class="panel"><form id="prefsForm" class="prefs-form">
    <fieldset class="wide"><legend>Sommerhus-brief</legend><label>Vores ønsker og mavefornemmelse<textarea name="wishes_note" rows="10">${esc(search.wishes_note || search.description || "")}</textarea></label></fieldset>
    <fieldset><legend>Budget-pejlemærker</legend><label>Minimumspris<input name="price_min" type="number" value="${esc(filters.price_min ?? "")}"></label><label>Makspris<input name="price_max" type="number" value="${esc(filters.price_max ?? "")}"></label><label>Maks kr/m²<input name="price_per_m2_max" type="number" value="${esc(filters.price_per_m2_max ?? "")}"></label></fieldset>
    <fieldset><legend>Hus-pejlemærker</legend><label>Minimum m²<input name="size_min" type="number" value="${esc(filters.size_min ?? "")}"></label><label>Maksimum m²<input name="size_max" type="number" value="${esc(filters.size_max ?? "")}"></label><label>Minimum værelser<input name="rooms_min" type="number" value="${esc(filters.rooms_min ?? "")}"></label><label>Minimum grund<input name="lot_size_min" type="number" value="${esc(filters.lot_size_min ?? "")}"></label></fieldset>
    <fieldset><legend>Beliggenhed-pejlemærker</legend><label>Regioner<input name="regions" value="${esc((filters.regions || []).join(", "))}"></label><label>Postnummer-prefix<input name="postal_codes" value="${esc((filters.postal_codes || []).join(", "))}"></label><label>Energimærker<input name="energy_ratings" value="${esc((filters.energy_ratings || []).join(", "))}"></label></fieldset>
    <fieldset class="wide"><legend>Nøgleord til agenten</legend><label>Kort beskrivelse<textarea name="description" rows="4">${esc(search.description || "")}</textarea></label><label>Positive nøgleord<input name="positive_keywords" value="${esc((search.positive_keywords || []).join(", "))}"></label><label>Negative nøgleord<input name="negative_keywords" value="${esc((search.negative_keywords || []).join(", "))}"></label></fieldset>
    <div class="form-actions"><button type="submit">Gem præferencer</button></div>
  </form></section>`;
  document.getElementById("prefsForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const num = (name) => form.elements[name].value === "" ? null : Number(form.elements[name].value);
    const split = (name) => form.elements[name].value.split(",").map((part) => part.trim()).filter(Boolean);
    await apiFetch("/api/preferences", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        ...prefs,
        filters: { ...filters, price_min: num("price_min"), price_max: num("price_max"), price_per_m2_max: num("price_per_m2_max"), size_min: num("size_min"), size_max: num("size_max"), rooms_min: num("rooms_min"), lot_size_min: num("lot_size_min"), regions: split("regions"), postal_codes: split("postal_codes"), energy_ratings: split("energy_ratings").map((value) => value.toUpperCase()) },
        search: { description: form.elements.description.value, wishes_note: form.elements.wishes_note.value, positive_keywords: split("positive_keywords"), negative_keywords: split("negative_keywords") },
      }),
    });
    toast("Præferencer gemt");
  });
}

async function openDetails(id) {
  const modal = document.getElementById("modal");
  const body = document.getElementById("modalBody");
  modal.classList.remove("hidden");
  document.body.classList.add("modal-open");
  body.innerHTML = `<div class="loading">Henter analyse...</div>`;
  const item = await apiFetch(`/api/listings/${id}/analysis`);
  const externalUrl = `/api/listings/${encodeURIComponent(id)}/broker-redirect`;
  body.innerHTML = `<article class="detail">
    ${item.image_url ? `<a class="detail-image" href="${esc(externalUrl)}" target="_blank" rel="noopener" aria-label="Åbn hos mægler" style="background-image:url('${esc(item.image_url)}')"></a>` : ""}
    <div class="detail-body">
      <div class="card-head"><div><h2>${esc(item.address || "Ukendt adresse")}</h2><p>${esc([item.postal_code, item.city, item.region].filter(Boolean).join(" · "))}</p></div><div class="score ${scoreTone(item.fit_score)}"><b>${Math.round(item.fit_score || 0)}</b><span>match</span></div></div>
      <div class="metrics detail-metrics">${metric("Pris", price(item.asking_price))}${metric("Kr/m²", item.price_per_m2 ? `${fmt(item.price_per_m2)} kr.` : "-")}${metric("Areal", item.size_m2 ? `${fmt(item.size_m2)} m²` : "-")}${metric("Værelser", item.rooms ?? "-")}${metric("Byggeår", item.year_built ?? "-")}${metric("Grund", item.lot_size ? `${fmt(item.lot_size)} m²` : "-")}${metric("Rejseproxy", travelLabel(item))}</div>
      <section><h3>Agentens vurdering</h3>${reasons(item, 8)}</section>
      ${geoRiskDetail(item)}
      <div class="card-actions"><button data-action="favorite" data-id="${esc(id)}">Favorit</button><button data-action="like" data-id="${esc(id)}">Like</button><button data-action="dislike" data-id="${esc(id)}" class="quiet">Dislike</button>${item.listing_url ? `<a href="${esc(externalUrl)}" target="_blank" rel="noopener">Mægler</a>` : ""}</div>
    </div>
  </article>`;
  attachActions(body);
}

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
  document.body.classList.remove("modal-open");
}

async function loadStats() {
  const stats = await apiFetch("/api/stats");
  document.getElementById("statActive").textContent = fmt(stats.active_count);
  document.getElementById("statPpm").textContent = fmt(Math.round(stats.avg_price_per_m2 || 0));
  document.getElementById("statTrend").textContent = (stats.seven_day_trend || []).map((row) => `${row.event_type}: ${row.count}`).join(" · ") || "Ingen";
  document.getElementById("statRun").textContent = stats.last_run?.finished_at ? stats.last_run.finished_at.slice(0, 16).replace("T", " ") : "Ingen";
}

async function generateRecommendations() {
  const button = document.getElementById("generateBtn");
  button.disabled = true;
  button.textContent = "Opdaterer...";
  setStatus("Genberegner match...");
  try {
    const result = await apiFetch("/api/recommendations/generate", { method: "POST" });
    allScoredListings = [];
    signalItemsCache.clear();
    setStatus(`Opdateret: ${result.item_count} anbefalinger`, "ok");
    await renderActiveView();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Genberegn match";
  }
}

async function runScrape() {
  const button = document.getElementById("scrapeBtn");
  button.disabled = true;
  button.textContent = "Henter...";
  setStatus("Henter nye annoncer fra Boliga...");
  try {
    const result = await apiFetch("/api/scrape", { method: "POST" });
    allScoredListings = [];
    signalItemsCache.clear();
    setStatus(`Hentet ${fmt(result.fetched)} annoncer`, "ok");
    await loadStats();
    await renderActiveView();
  } catch (error) {
    setStatus(error.message, "error");
  } finally {
    button.disabled = false;
    button.textContent = "Hent nye annoncer";
  }
}

async function init() {
  watchedIds = new Set((await apiFetch("/api/watchlist")).map((item) => String(item.listing_id)));
  document.querySelectorAll(".nav-tab").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  document.getElementById("generateBtn").addEventListener("click", generateRecommendations);
  document.getElementById("scrapeBtn").addEventListener("click", runScrape);
  document.getElementById("modalClose").addEventListener("click", closeModal);
  document.getElementById("modalBackdrop").addEventListener("click", closeModal);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeModal(); });
  await loadStats();
  await renderMatch();
}

init().catch((error) => {
  document.getElementById("appMain").innerHTML = `<div class="empty">${esc(error.message)}</div>`;
});
