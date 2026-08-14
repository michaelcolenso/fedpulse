/* FedPulse v0.2 evidence-first dashboard. */
"use strict";
const state = { daily: {}, packages: [], standalone: [], metrics: [], marc: [], health: {}, brief: {} };
const $ = (id) => document.getElementById(id);
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c])); }
function safeUrl(value) { const raw = String(value ?? ""); return /^https:\/\//i.test(raw) ? raw : "#"; }
function text(value, fallback = "—") { return esc(value == null || value === "" ? fallback : value); }
function evidenceLinks(evidence) {
  return (evidence || []).map((e) => `<a class="evidence-link" href="${esc(safeUrl(e.official_url))}" target="_blank" rel="noopener noreferrer">${text(e.title || e.record_id)} ↗</a>`).join("");
}
function packageMatches(p) {
  const values = {
    "agency-filter": [p.canonical_agency_name, p.coordination_agency_id, ...(p.raw_agency_names || [])].join(" ").toLowerCase(),
    "direction-filter": String(p.direction || "").toLowerCase(),
    "sector-filter": (p.coverage_tags || []).map((x) => x.sector).join(" ").toLowerCase(),
    "family-filter": Object.keys(p.document_type_counts || {}).join(" ").toLowerCase(),
  };
  return Object.entries(values).every(([id, value]) => { const q = ($(id).value || "").trim().toLowerCase(); return !q || value.includes(q); });
}
function renderFreshness() {
  const entries = Object.entries(state.health.source_freshness || {});
  if (!entries.length) { $("freshness").textContent = "No source health snapshot yet."; return; }
  const bad = entries.filter(([, v]) => !["fresh", "running"].includes(v.status));
  $("freshness").className = `banner ${bad.length ? "degraded" : "fresh"}`;
  $("freshness").innerHTML = `<strong>${bad.length ? "Degraded source" : "Sources healthy"}</strong> · ${entries.map(([k, v]) => `${esc(k)}: ${esc(v.status)}${v.last_publication_date ? ` · last FR ${esc(v.last_publication_date)}` : ""}${v.last_cataloged_date ? ` · last MARC ${esc(v.last_cataloged_date)}` : ""}`).join(" · ")}`;
}
function renderDaily() {
  const d = state.daily;
  $("daily").innerHTML = `<div class="total-number">${text(d.total_records, "0")}</div><div><div class="muted">Federal Register records on ${text(d.date)}</div><div class="chips">${Object.entries(d.document_type_counts || {}).map(([k,v]) => `<span class="chip">${esc(k)} <b>${text(v,"0")}</b></span>`).join("") || `<span class="muted">No records in the daily snapshot.</span>`}</div></div>`;
}
function renderPackages() {
  const wantedConfidence = $("confidence-filter").value; const wantedLifecycle = $("lifecycle-filter").value;
  const items = state.packages.filter((p) => (!wantedConfidence || p.confidence === wantedConfidence) && (!wantedLifecycle || (p.lifecycle || "new") === wantedLifecycle) && packageMatches(p));
  $("package-count").textContent = String(items.length);
  $("packages").innerHTML = items.length ? items.map((p) => `<article class="card ${p.confidence === "low" ? "low-confidence" : ""} ${esc(p.confidence || "unknown")}"><div class="card-top"><h3>${text(p.label || p.canonical_agency_name)}</h3><span class="badge ${esc(p.confidence)}">${text(p.confidence)}</span></div><p class="meta">${text(p.date_start)} → ${text(p.date_end)} · ${text(p.direction)} · ${text(p.lifecycle || "new")} · ${text(p.record_count,"0")} records</p><p class="meta">coordination: ${text(p.coordination_agency_id || p.agency_id)} · taxonomy ${esc(JSON.stringify(p.taxonomy_versions || {}))}</p><p class="meta">priority: ${esc(Object.entries(p.priority_components || {}).map(([key,value]) => `${key}=${value}`).join(" · "))}</p><details><summary>Evidence (${esc((p.evidence || []).length)})</summary><div class="evidence">${evidenceLinks(p.evidence)}<p class="meta">${(p.confidence_reasons || []).map(text).join(" · ")}</p></div></details></article>`).join("") : `<div class="empty">No packages match these filters.</div>`;
}
function renderStandalone() {
  $("standalone-count").textContent = String(state.standalone.length);
  $("standalone").innerHTML = state.standalone.length ? state.standalone.map((s) => `<article class="card"><div class="card-top"><h3>${text(s.canonical_agency_name || s.raw_agency_name)}</h3><span class="badge watch">watchlist</span></div><p>${text(s.title)}</p><p class="meta">${text(s.doc_type)} · ${text(s.publication_date)} · ${text(s.lifecycle || "new")}</p><p class="meta">${(s.matches || []).map((m) => `${esc(m.watchlist)}: ${esc(m.rule)}`).join(" · ")}</p><details><summary>Record evidence</summary><div class="evidence">${evidenceLinks([{official_url:s.official_url,title:s.title,record_id:s.record_id}])}</div></details></article>`).join("") : `<div class="empty">No standalone watchlist matches.</div>`;
}
function renderMetrics() {
  const wrappers = state.metrics;
  $("fr-metrics").innerHTML = wrappers.length ? wrappers.map((m) => { const body = (m.items || []).slice(0, 80).map((x) => `<div class="metric-row ${x.alert ? "flag" : ""}"><span>${text(x.agency || x.agency_id || x.signal_type || m.metric)}</span><strong>${x.z_score != null ? `z ${text(x.z_score)}` : x.proposal_to_final_ratio != null ? `ratio ${text(x.proposal_to_final_ratio)}` : x.recent_weekly_rate != null ? `rate ${text(x.recent_weekly_rate)}` : x.alert ? "alert" : "—"}</strong><span class="meta">${x.alert ? "alert" : "supporting metric"} · ${text(x.statistical_evidence || x.alert_basis || "per-agency")}</span></div>`).join(""); return `<article class="card"><div class="card-top"><h3>${text(m.metric)}</h3><span class="badge metric">${m.alert ? "alert" : "support"}</span></div><p class="meta">${text(m.as_of)} · ${text(m.as_of_timezone)}</p>${body || `<p class="muted">No per-agency rows.</p>`}</article>`; }).join("") : `<div class="empty">No FR metrics snapshot.</div>`;
}
function renderMarc() {
  $("marc").innerHTML = state.marc.length ? state.marc.map((m) => `<article class="card ${m.confidence === "insufficient_sample" || m.confidence === "catalog_batch_risk" ? "low-confidence" : ""}"><div class="card-top"><h3>${text(m.subject)}</h3><span class="badge ${esc(m.confidence)}">${text(m.confidence)}</span></div><p class="meta">${text(m.last_four_week_catalog_count,"0")} cataloged · ${text(m.distinct_cataloged_dates,"0")} dates · ${text(m.distinct_canonical_agencies,"0")} agencies · ${text(m.first_seen_label)}</p><details><summary>Catalog evidence (${esc((m.evidence || []).length)})</summary><div class="evidence">${evidenceLinks((m.evidence || []).slice(0, 20))}</div></details></article>`).join("") : `<div class="empty">No MARC horizon snapshot.</div>`;
}
async function load() {
  try {
    const [daily, packages, standalone, frMetrics, marc, health, brief] = await Promise.all([
      fetch("../data/outputs/current/daily_activity.json").then((r) => r.json()),
      fetch("../data/outputs/current/packages.json").then((r) => r.json()),
      fetch("../data/outputs/current/standalone.json").then((r) => r.json()),
      fetch("../data/outputs/current/fr_metrics.json").then((r) => r.json()),
      fetch("../data/outputs/current/marc_horizon.json").then((r) => r.json()),
      fetch("../data/outputs/current/health.json").then((r) => r.json()),
      fetch("../data/outputs/current/brief.json").then((r) => r.json()),
    ]);
    for (const payload of [daily, packages, standalone, frMetrics, marc, health, brief]) {
      if (payload.schema_version !== 2) throw new Error("unsupported output schema");
    }
    state.daily = (daily.items || [])[0] || {}; state.packages = packages.items || []; state.standalone = standalone.items || []; state.metrics = frMetrics.items || []; state.marc = marc.items || []; state.health = health; state.brief = brief;
    $("asof").textContent = `as of ${health.as_of || brief.as_of || "—"}`; $("status").textContent = `loaded schema-v2 · ${state.packages.length} packages · ${state.standalone.length} standalone · ${state.marc.length} MARC topics`;
  } catch (error) { $("status").textContent = `schema-v2 output unavailable: ${error.message}`; }
  renderFreshness(); renderDaily(); renderPackages(); renderStandalone(); renderMetrics(); renderMarc();
}
["agency-filter", "direction-filter", "sector-filter", "family-filter", "confidence-filter", "lifecycle-filter"].forEach((id) => $(id).addEventListener("input", renderPackages));
load();
