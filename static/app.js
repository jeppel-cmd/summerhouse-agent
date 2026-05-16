"use strict";

const kr = new Intl.NumberFormat("da-DK");

let activeView = "match";
let activeSignal = "daily";
let watchedIds = new Set();
let selectedAreas = new Set();
let allScoredListings = [];

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
  daily: { label: "Bedste match", endpoint: "/api/map/listings?limit=5000", title: "Bedste match lige nu" },
  ai: { label: "AI fremhævede", endpoint: "/api/agent/ai-highlights", title: "Matcher jeres beskrivelse" },
  price: { label: "Prisfald", endpoint: "/api/agent/price-drops", title: "Interessante prisfald" },
  gems: { label: "Perler", endpoint: "/api/agent/hidden-gems", title: "Skjulte perler" },
  open: { label: "Fremvisninger", endpoint: "/api/agent/open-houses", title: "Kommende fremvisninger" },
};

const mapAreas = [
  {
    id: "north",
    name: "Nord",
    hint: "Nordkysten, Hornbæk, Gilleleje",
    prefixes: ["30", "31", "32", "33", "34", "35", "36"],
    d: "M180 52 C248 12 342 28 400 82 C448 126 466 184 444 232 C393 214 332 206 276 218 C224 229 174 251 126 235 C110 160 124 88 180 52 Z",
    labelX: 250,
    labelY: 122,
  },
  {
    id: "east",
    name: "Øst",
    hint: "Roskilde, Køge, Stevns",
    prefixes: ["26", "27", "28", "29", "40", "41", "46"],
    d: "M276 218 C332 206 393 214 444 232 C431 286 400 329 419 386 C438 444 500 478 474 546 C425 528 367 487 322 438 C282 394 254 333 252 270 C251 248 260 232 276 218 Z",
    labelX: 350,
    labelY: 336,
  },
  {
    id: "west",
    name: "Vest",
    hint: "Odsherred, Holbæk, Kalundborg",
    prefixes: ["42", "43", "44", "45"],
    d: "M126 235 C174 251 224 229 276 218 C260 232 251 248 252 270 C254 333 282 394 322 438 C263 452 202 456 151 424 C98 391 75 337 84 286 C90 253 103 238 126 235 Z",
    labelX: 145,
    labelY: 332,
  },
  {
    id: "south",
    name: "Syd",
    hint: "Næstved, Møn, Lolland-Falster",
    prefixes: ["47", "48", "49"],
    d: "M151 424 C202 456 263 452 322 438 C367 487 425 528 474 546 C456 618 379 668 301 646 C248 631 229 586 178 552 C124 516 98 470 151 424 Z M132 616 C216 586 353 587 441 614 C483 626 480 666 424 687 C334 719 188 698 120 665 C87 649 91 631 132 616 Z",
    labelX: 238,
    labelY: 552,
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

async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function areaForItem(item) {
  const postal = String(item.postal_code || "");
  return mapAreas.find((area) => area.prefixes.some((prefix) => postal.startsWith(prefix))) || null;
}

function matchesSelectedArea(item) {
  if (!selectedAreas.size) return true;
  const area = areaForItem(item);
  return area ? selectedAreas.has(area.id) : false;
}

function metric(label, value) {
  return `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

function badges(item) {
  const out = [];
  if (item.hidden_gem) out.push("Perle");
  if (item.motivated_seller) out.push("Motiveret sælger");
  if (item.recommendation_reasons?.length) out.push("AI");
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
  return `<article class="listing-card${options.compact ? " compact" : ""}">
    ${item.image_url ? `<button class="image-button" data-action="details" data-id="${esc(id)}" style="background-image:url('${esc(item.image_url)}')"></button>` : `<button class="image-button empty" data-action="details" data-id="${esc(id)}"></button>`}
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
      ${options.compact ? "" : reasons(item)}
      <div class="card-actions">
        <button data-action="favorite" data-id="${esc(id)}" class="${watchedIds.has(id) ? "active" : ""}">Favorit</button>
        <button data-action="like" data-id="${esc(id)}">Like</button>
        <button data-action="dislike" data-id="${esc(id)}" class="quiet">Dislike</button>
        <button data-action="details" data-id="${esc(id)}" class="quiet">Detaljer</button>
        ${item.listing_url ? `<a href="${esc(item.listing_url)}" target="_blank" rel="noopener">Boliga</a>` : ""}
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
    <p>${totalAfter} af ${totalBefore} huse matcher filtrene.</p>
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
      renderMatch();
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
  if (activeView === "map") return renderMap();
  if (activeView === "favorites") return renderFavorites();
  if (activeView === "preferences") return renderPreferences();
}

async function itemsForSignal(signalKey) {
  const config = signals[signalKey];
  const items = await apiFetch(config.endpoint);
  return signalKey === "daily"
    ? items.sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0)).slice(0, 250)
    : items;
}

async function renderMatch() {
  const config = signals[activeSignal];
  const items = await itemsForSignal(activeSignal);
  if (activeSignal === "open") return renderOpenHouseDates(items);
  const filtered = applyMatchFilters(items);
  const displayItems = filtered.slice(0, 60);
  const main = document.getElementById("appMain");
  main.innerHTML = `<section class="page-head">
    <div>
      <span class="eyebrow">Agentens shortlist</span>
      <h2>Match</h2>
      <p>Kortvalg og filtre opdaterer listen med det samme. Genberegn kun når nye data eller scoring skal opdateres.</p>
    </div>
    <div class="signal-tabs">
      ${Object.entries(signals).map(([key, signal]) => `<button class="${key === activeSignal ? "active" : ""}" data-signal="${key}">${signal.label}</button>`).join("")}
    </div>
  </section>
  <section class="match-layout">
    ${filterPanel(items.length, filtered.length)}
    <div class="panel">
      <div class="section-title"><h3>${esc(config.title)}</h3><span>${displayItems.length} vist</span></div>
      ${displayItems.length ? `<div class="card-grid">${displayItems.map((item) => card(item)).join("")}</div>` : `<div class="empty">Ingen huse matcher filtrene.</div>`}
    </div>
  </section>`;
  main.querySelectorAll("[data-signal]").forEach((button) => button.addEventListener("click", () => {
    activeSignal = button.dataset.signal;
    renderMatch();
  }));
  attachFilterListeners(main);
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
    <div class="signal-tabs">${Object.entries(signals).map(([key, signal]) => `<button class="${key === activeSignal ? "active" : ""}" data-signal="${key}">${signal.label}</button>`).join("")}</div>
  </section>
  <section class="open-layout">
    <aside class="date-list">
      <h3>Datoer</h3>
      ${groups.length ? groups.map((group, index) => `<button class="date-card ${index === 0 ? "active" : ""}" data-date="${group.key}"><strong>${esc(group.label)}</strong><span>${group.items.length} huse</span></button>`).join("") : `<div class="empty mini">Ingen kommende fremvisninger.</div>`}
    </aside>
    <div class="panel open-results"><div id="openHouseResults"></div></div>
  </section>`;
  main.querySelectorAll("[data-signal]").forEach((button) => button.addEventListener("click", () => {
    activeSignal = button.dataset.signal;
    renderMatch();
  }));
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
  allScoredListings = allScoredListings.length ? allScoredListings : await apiFetch("/api/map/listings?limit=5000");
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
    <div><span class="eyebrow">Geografisk overblik</span><h2>Kort</h2><p>Klik nord, syd, øst eller vest til/fra. Valget bruges også direkte i Match.</p></div>
    <div class="map-actions"><button id="clearAreas" class="quiet">Ryd områdevalg</button></div>
  </section>
  <section class="map-layout">
    <div class="area-map" aria-label="Klikbart områdekort over Sjælland">
      <svg viewBox="0 0 620 720" role="img" aria-label="Grafisk kort over Sjælland">
        <rect class="map-water" x="0" y="0" width="620" height="720"></rect>
        ${mapAreas.map((area) => `<g class="region-shape ${selectedAreas.has(area.id) ? "selected" : ""}" data-area="${area.id}">
          <path d="${area.d}"></path>
          <text x="${area.labelX}" y="${area.labelY}">${esc(area.name)}</text>
          <text class="area-count" x="${area.labelX}" y="${area.labelY + 24}">${counts[area.id] || 0} huse</text>
        </g>`).join("")}
      </svg>
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
  main.innerHTML = `<section class="page-head"><div><span class="eyebrow">Hvad leder vi efter?</span><h2>Præferencer</h2><p>Budget, område og fritekst bruges af agentens scoring og AI fremhævede.</p></div></section>
  <section class="panel"><form id="prefsForm" class="prefs-form">
    <fieldset><legend>Budget</legend><label>Minimumspris<input name="price_min" type="number" value="${esc(filters.price_min ?? "")}"></label><label>Makspris<input name="price_max" type="number" value="${esc(filters.price_max ?? "")}"></label><label>Maks kr/m²<input name="price_per_m2_max" type="number" value="${esc(filters.price_per_m2_max ?? "")}"></label></fieldset>
    <fieldset><legend>Hus</legend><label>Minimum m²<input name="size_min" type="number" value="${esc(filters.size_min ?? "")}"></label><label>Maksimum m²<input name="size_max" type="number" value="${esc(filters.size_max ?? "")}"></label><label>Minimum værelser<input name="rooms_min" type="number" value="${esc(filters.rooms_min ?? "")}"></label><label>Minimum grund<input name="lot_size_min" type="number" value="${esc(filters.lot_size_min ?? "")}"></label></fieldset>
    <fieldset><legend>Beliggenhed</legend><label>Regioner<input name="regions" value="${esc((filters.regions || []).join(", "))}"></label><label>Postnummer-prefix<input name="postal_codes" value="${esc((filters.postal_codes || []).join(", "))}"></label><label>Energimærker<input name="energy_ratings" value="${esc((filters.energy_ratings || []).join(", "))}"></label></fieldset>
    <fieldset class="wide"><legend>AI fremhævede</legend><label>Beskrivelse<textarea name="description" rows="5">${esc(search.description || "")}</textarea></label><label>Positive nøgleord<input name="positive_keywords" value="${esc((search.positive_keywords || []).join(", "))}"></label><label>Negative nøgleord<input name="negative_keywords" value="${esc((search.negative_keywords || []).join(", "))}"></label></fieldset>
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
        search: { description: form.elements.description.value, positive_keywords: split("positive_keywords"), negative_keywords: split("negative_keywords") },
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
  body.innerHTML = `<article class="detail">
    ${item.image_url ? `<div class="detail-image" style="background-image:url('${esc(item.image_url)}')"></div>` : ""}
    <div class="detail-body">
      <div class="card-head"><div><h2>${esc(item.address || "Ukendt adresse")}</h2><p>${esc([item.postal_code, item.city, item.region].filter(Boolean).join(" · "))}</p></div><div class="score ${scoreTone(item.fit_score)}"><b>${Math.round(item.fit_score || 0)}</b><span>match</span></div></div>
      <div class="metrics detail-metrics">${metric("Pris", price(item.asking_price))}${metric("Kr/m²", item.price_per_m2 ? `${fmt(item.price_per_m2)} kr.` : "-")}${metric("Areal", item.size_m2 ? `${fmt(item.size_m2)} m²` : "-")}${metric("Værelser", item.rooms ?? "-")}${metric("Byggeår", item.year_built ?? "-")}${metric("Grund", item.lot_size ? `${fmt(item.lot_size)} m²` : "-")}${metric("Rejseproxy", travelLabel(item))}</div>
      <section><h3>Agentens vurdering</h3>${reasons(item, 8)}</section>
      <section><h3>Oversvømmelsesrisiko</h3><p>${esc(item.flood_risk?.warning_text || "Ikke undersøgt endnu.")}</p></section>
      <div class="card-actions"><button data-action="favorite" data-id="${esc(id)}">Favorit</button><button data-action="like" data-id="${esc(id)}">Like</button><button data-action="dislike" data-id="${esc(id)}" class="quiet">Dislike</button>${item.listing_url ? `<a href="${esc(item.listing_url)}" target="_blank" rel="noopener">Boliga</a>` : ""}</div>
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
