"use strict";

const kr = new Intl.NumberFormat("da-DK");
let todayItems = [];
let todayPayload = { history: [], date: null, generated_at: null };
let selectedDate = new URLSearchParams(window.location.search).get("date") || null;

function esc(value) {
  const div = document.createElement("div");
  div.textContent = String(value ?? "");
  return div.innerHTML;
}

function fmt(value) {
  return value != null && value !== "" ? kr.format(value) : "-";
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
  return parsed.toLocaleString("da-DK", { weekday: "short", day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}

function metric(label, value) {
  return `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`;
}

async function apiFetch(url, options = {}) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function toast(message, tone = "ok") {
  const el = document.getElementById("toast");
  el.textContent = message;
  el.className = `toast toast-${tone} visible`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.className = "toast"; }, 2400);
}

function setStatus(message, tone = "") {
  const el = document.getElementById("todayStatus");
  el.textContent = message || "";
  el.className = `global-status ${tone}`;
}

function travelLabel(item) {
  const publicMinutes = item.score_components?.estimated_public_transport_minutes;
  const carMinutes = item.score_components?.estimated_car_minutes;
  if (!publicMinutes && !carMinutes) return "Tjek adresse";
  return `${publicMinutes || "-"} min off. / ${carMinutes || "-"} min bil`;
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

function reasons(item, limit = 3) {
  const list = (item.reasons || item.recommendation_reasons || []).slice(0, limit);
  if (!list.length) return "";
  return `<ul class="reason-list">${list.map((reason) => `<li>${esc(reason)}</li>`).join("")}</ul>`;
}

function badges(item) {
  const out = [];
  if (item.hidden_gem) out.push("Perle");
  if (item.motivated_seller) out.push("Motiveret sælger");
  if (item.recommendation_reasons?.length || item.reasons?.length) out.push("Agentbegrundet");
  if (item.score_components?.area_research_name) out.push(`Område: ${item.score_components.area_research_name}`);
  const oh = formatDate(item.open_house);
  if (oh) out.push(`Fremvisning ${oh}`);
  return out.map((badge) => `<span class="badge">${esc(badge)}</span>`).join("");
}

function topCard(item, index) {
  const id = String(item.listing_id);
  const externalUrl = `/api/listings/${encodeURIComponent(id)}/broker-redirect`;
  const image = item.image_url
    ? `<a class="today-rank-image" href="${esc(externalUrl)}" target="_blank" rel="noopener" aria-label="Åbn hos mægler" style="background-image:url('${esc(item.image_url)}')"></a>`
    : `<a class="today-rank-image empty" href="${esc(externalUrl)}" target="_blank" rel="noopener" aria-label="Åbn hos mægler"></a>`;
  return `<article class="today-rank-card">
    <div class="today-rank-number">#${index + 1}</div>
    ${image}
    <div class="today-rank-body">
      <div class="card-head">
        <div>
          <h2>${esc(item.address || "Ukendt adresse")}</h2>
          <p>${esc([item.postal_code, item.city].filter(Boolean).join(" "))}${item.region ? ` · ${esc(item.region)}` : ""}</p>
        </div>
      </div>
      <div class="badge-row">${badges(item)}</div>
      <div class="metrics today-metrics">
        ${metric("Pris", price(item.asking_price))}
        ${metric("Kr/m²", item.price_per_m2 ? `${fmt(item.price_per_m2)} kr.` : "-")}
        ${metric("Areal", item.size_m2 ? `${fmt(item.size_m2)} m²` : "-")}
        ${metric("Værelser", item.rooms ?? "-")}
        ${metric("Rejse", travelLabel(item))}
      </div>
      ${geoRiskSummary(item)}
      ${reasons(item, 4)}
      <div class="card-actions">
        <a href="${esc(externalUrl)}" target="_blank" rel="noopener">Åbn hos mægler</a>
        <a href="/" class="quiet-link">Åbn privat dashboard</a>
      </div>
    </div>
  </article>`;
}

function prettyDate(value) {
  if (!value) return "Dagens liste";
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("da-DK", { weekday: "short", day: "numeric", month: "short" });
}

function generatedTime(value) {
  if (!value) return "-";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return String(value).slice(11, 16) || "-";
  return parsed.toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
}

function updateUrlDate(date) {
  const url = new URL(window.location.href);
  if (date) url.searchParams.set("date", date);
  else url.searchParams.delete("date");
  window.history.replaceState({}, "", url);
}

function renderHistory() {
  const target = document.getElementById("todayHistoryList");
  const history = todayPayload.history || [];
  if (!history.length) {
    target.innerHTML = `<div class="empty mini">Ingen historik endnu.</div>`;
    return;
  }
  target.innerHTML = history.map((entry) => {
    const active = entry.date === todayPayload.date;
    const label = entry.date === history[0]?.date ? "Seneste" : prettyDate(entry.date);
    return `<button class="history-day ${active ? "active" : ""}" data-date="${esc(entry.date)}">
      <strong>${esc(label)}</strong>
      <span>${esc(entry.date)} · ${esc(entry.item_count || 0)} huse</span>
    </button>`;
  }).join("");
  target.querySelectorAll("[data-date]").forEach((button) => {
    button.addEventListener("click", () => loadToday(button.dataset.date));
  });
}

function renderToday() {
  const target = document.getElementById("todayList");
  const topFive = todayItems.slice(0, 5);
  document.getElementById("todayDate").textContent = prettyDate(todayPayload.date);
  document.getElementById("todayCount").textContent = `${topFive.length}/5`;
  document.getElementById("todayUpdated").textContent = generatedTime(todayPayload.generated_at);
  target.innerHTML = topFive.length
    ? topFive.map((item, index) => topCard(item, index)).join("")
    : `<div class="empty">Der er ingen dagsliste for denne dato endnu.</div>`;
  renderHistory();
}

async function loadToday(date = selectedDate) {
  setStatus("");
  selectedDate = date || null;
  updateUrlDate(selectedDate);
  document.getElementById("todayRefresh").disabled = true;
  try {
    const url = selectedDate ? `/api/public/today?date=${encodeURIComponent(selectedDate)}` : "/api/public/today";
    todayPayload = await apiFetch(url);
    todayItems = todayPayload.items || [];
    renderToday();
  } catch (error) {
    setStatus(error.message, "error");
    document.getElementById("todayList").innerHTML = `<div class="empty">Kunne ikke hente dagens top 5: ${esc(error.message)}</div>`;
  } finally {
    document.getElementById("todayRefresh").disabled = false;
  }
}

function init() {
  document.getElementById("todayDate").textContent = "-";
  document.getElementById("todayRefresh").addEventListener("click", () => loadToday(selectedDate));
  loadToday();
}

init();
