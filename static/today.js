"use strict";

const kr = new Intl.NumberFormat("da-DK");
let watchedIds = new Set();
let todayItems = [];

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
    : `<button class="today-rank-image empty" data-action="details" data-id="${esc(id)}" aria-label="Åbn detaljer"></button>`;
  return `<article class="today-rank-card">
    <div class="today-rank-number">#${index + 1}</div>
    ${image}
    <div class="today-rank-body">
      <div class="card-head">
        <div>
          <h2>${esc(item.address || "Ukendt adresse")}</h2>
          <p>${esc([item.postal_code, item.city].filter(Boolean).join(" "))}${item.region ? ` · ${esc(item.region)}` : ""}</p>
        </div>
        <div class="score ${scoreTone(item.fit_score)}"><b>${item.fit_score != null ? Math.round(item.fit_score) : "-"}</b><span>match</span></div>
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
        <button data-action="favorite" data-id="${esc(id)}" class="${watchedIds.has(id) ? "active" : ""}">${watchedIds.has(id) ? "Favorit ✓" : "Favorit"}</button>
        <button data-action="details" data-id="${esc(id)}" class="quiet">Detaljer</button>
        <a href="${esc(externalUrl)}" target="_blank" rel="noopener">Mægler</a>
      </div>
    </div>
  </article>`;
}

function renderToday() {
  const target = document.getElementById("todayList");
  const topFive = [...todayItems].sort((a, b) => (b.fit_score || 0) - (a.fit_score || 0)).slice(0, 5);
  document.getElementById("todayCount").textContent = `${topFive.length}/5`;
  document.getElementById("todayUpdated").textContent = new Date().toLocaleTimeString("da-DK", { hour: "2-digit", minute: "2-digit" });
  target.innerHTML = topFive.length
    ? topFive.map((item, index) => topCard(item, index)).join("")
    : `<div class="empty">Der er ingen dagsliste endnu. Åbn dashboardet og tryk “Genberegn match”.</div>`;
  attachActions(target);
}

async function loadToday() {
  setStatus("");
  document.getElementById("todayRefresh").disabled = true;
  try {
    const [watchlist, daily] = await Promise.all([apiFetch("/api/watchlist"), apiFetch("/api/agent/daily")]);
    watchedIds = new Set(watchlist.map((item) => String(item.listing_id)));
    todayItems = daily;
    renderToday();
  } catch (error) {
    setStatus(error.message, "error");
    document.getElementById("todayList").innerHTML = `<div class="empty">Kunne ikke hente dagens top 5: ${esc(error.message)}</div>`;
  } finally {
    document.getElementById("todayRefresh").disabled = false;
  }
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
      return renderToday();
    }
  } catch (error) {
    toast(error.message, "err");
  }
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
      <div class="card-actions"><button data-action="favorite" data-id="${esc(id)}">Favorit</button><a href="${esc(externalUrl)}" target="_blank" rel="noopener">Mægler</a></div>
    </div>
  </article>`;
  attachActions(body);
}

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
  document.body.classList.remove("modal-open");
}

function init() {
  document.getElementById("todayDate").textContent = new Date().toLocaleDateString("da-DK", { weekday: "long", day: "numeric", month: "long" });
  document.getElementById("todayRefresh").addEventListener("click", loadToday);
  document.getElementById("modalClose").addEventListener("click", closeModal);
  document.getElementById("modalBackdrop").addEventListener("click", closeModal);
  document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeModal(); });
  loadToday();
}

init();
