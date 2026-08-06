/* FedPulse dashboard — reads ../data/outputs/*.json, renders three index panels.
   Dependency-free vanilla JS. Serve over HTTP (fetch fails on file://).
   XSS note: all interpolated values pass through esc() before entering innerHTML. */
"use strict";

const state = { api: [], rcr: [], terNew: [], terAccel: [], mode: "new" };

const $ = (id) => document.getElementById(id);

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

function spark(series) {
  if (!series || !series.length) return "";
  const max = Math.max(...series.map((s) => s.count), 1);
  const bars = series.map((s) => {
    const h = Math.max(2, Math.round((s.count / max) * 100));
    return `<i style="height:${h}%" title="${s.week} · ${s.count}"></i>`;
  }).join("");
  return `<div class="spark">${bars}</div>`;
}

function renderApi() {
  const q = ($("api-filter").value || "").toLowerCase();
  const items = state.api.filter((a) => !q || a.agency.toLowerCase().includes(q));
  $("api-count").textContent = items.filter((a) => a.flagged).length;
  const list = $("api-list");
  if (!items.length) { list.innerHTML = '<div class="empty">No agencies match.</div>'; return; }
  list.innerHTML = items.map((a) => `
    <div class="item ${a.flagged ? "flag" : ""}">
      <div class="row1">
        <span class="name">${esc(a.agency)}</span>
        <span class="val">z ${a.z_score == null ? "—" : a.z_score}</span>
      </div>
      <div class="meta">week ${esc(a.current_week || "—")} · ${a.current_count} rec · baseline ${a.baseline_mean}/wk${a.flagged ? " · FLAGGED" : ""}</div>
      ${spark(a.series)}
    </div>`).join("");
}

function renderRcr() {
  const q = ($("rcr-filter").value || "").toLowerCase();
  const items = state.rcr.filter((a) => !q || a.agency.toLowerCase().includes(q));
  $("rcr-count").textContent = items.filter((a) => a.flagged).length;
  const list = $("rcr-list");
  if (!items.length) { list.innerHTML = '<div class="empty">No agencies match.</div>'; return; }
  list.innerHTML = items.map((a) => `
    <div class="item ${a.flagged ? "flag" : ""}">
      <div class="row1">
        <span class="name">${esc(a.agency)}</span>
        <span class="val">${a.churn_ratio == null ? "—" : a.churn_ratio + ":1"}</span>
      </div>
      <div class="meta">${a.final_rules} final · ${a.proposed_rules} prop · ${a.notices} notices · ${a.window_start} → ${a.window_end}</div>
    </div>`).join("");
}

function renderTer() {
  const q = ($("ter-filter").value || "").toLowerCase();
  const src = state.mode === "new" ? state.terNew : state.terAccel;
  const items = src.filter((s) => !q || (s.subject || "").toLowerCase().includes(q));
  $("ter-count").textContent = items.length;
  const list = $("ter-list");
  if (!items.length) { list.innerHTML = '<div class="empty">No subjects match.</div>'; return; }
  list.innerHTML = items.map((s) => {
    const meta = state.mode === "new"
      ? `first seen ${esc(s.first_seen || "—")} · ${esc(s.agency || "—")}`
      : `last 4w ${s.last_4w_count} · prior mean ${s.prior_weekly_mean}/wk · ${s.multiple}x`;
    return `
      <div class="item flag">
        <div class="row1">
          <span class="name">${esc(s.subject)}</span>
          <span class="val">${state.mode === "new" ? "NEW" : s.multiple + "×"}</span>
        </div>
        <div class="meta">${meta}</div>
      </div>`;
  }).join("");
}

async function load() {
  try {
    const [api, rcr, ter, summary] = await Promise.all([
      fetch("../data/outputs/api.json").then((r) => r.json()),
      fetch("../data/outputs/rcr.json").then((r) => r.json()),
      fetch("../data/outputs/ter.json").then((r) => r.json()),
      fetch("../data/outputs/summary.json").then((r) => r.json()),
    ]);
    state.api = api.agencies || [];
    state.rcr = rcr.agencies || [];
    state.terNew = ter.new_subjects || [];
    state.terAccel = ter.accelerating_subjects || [];
    $("asof").textContent = "as of " + (api.as_of || "—");
    $("status").textContent = `loaded · ${state.api.length} agencies · ${state.rcr.length} churn rows · ${state.terNew.length} new subjects · ${state.terAccel.length} accelerating`;
  } catch (e) {
    $("status").textContent = "no index data yet — first ingest pending";
  }
  renderApi(); renderRcr(); renderTer();
}

["api-filter", "rcr-filter", "ter-filter"].forEach((id) =>
  $(id).addEventListener("input", () =>
    (id === "api-filter" ? renderApi() : id === "rcr-filter" ? renderRcr() : renderTer())
  )
);
document.getElementById("ter-seg").addEventListener("click", (e) => {
  const btn = e.target.closest("button");
  if (!btn) return;
  state.mode = btn.dataset.mode;
  document.querySelectorAll("#ter-seg button").forEach((b) => b.classList.toggle("active", b === btn));
  renderTer();
});

load();
