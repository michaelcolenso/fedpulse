"use strict";

const state = { daily: {}, packages: [], standalone: [], metrics: [], marc: [], health: {}, brief: {}, generation: "—" };
const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
const text = (value, fallback = "—") => esc(value == null || value === "" ? fallback : value);
const safeUrl = (value) => /^https:\/\//i.test(String(value ?? "")) ? String(value) : "#";
const confidenceRank = { high: 0, medium: 1, low: 2 };

function evidenceLinks(evidence, limit = 6) {
  const rows = (evidence || []).slice(0, limit).map((e) => `<a class="evidence-link" href="${esc(safeUrl(e.official_url))}" target="_blank" rel="noopener noreferrer">${text(e.title || e.record_id)} ↗</a>`).join("");
  const extra = (evidence || []).length > limit ? `<span class="muted">+${(evidence || []).length - limit} more official records</span>` : "";
  return rows + extra;
}

function packageSectors(p) {
  return [...new Set((p.coverage_tags || []).map((x) => x.sector).filter(Boolean))];
}

function whyFlagged(p) {
  return p.selection_reason || (p.confidence_reasons || []).slice(0, 2).join(" · ") || "Several official records moved together around the same bounded issue.";
}

function whoMayCare(p) {
  const sectors = packageSectors(p);
  if (sectors.length) return sectors.slice(0, 4).join(", ");
  return p.canonical_agency_name ? `Organizations affected by ${p.canonical_agency_name} actions` : "Organizations exposed to this federal activity";
}

function actionFor(p) {
  if (p.lifecycle === "resolved") return "Review the outcome and close or update any related watch item.";
  if (p.confidence === "high" && p.notify) return "Review the evidence now and decide whether this needs an owner.";
  if (p.lifecycle === "new") return "Monitor. This is new activity; no immediate action is implied yet.";
  return "Keep watching. Activity is meaningful, but the evidence does not yet imply an immediate response.";
}

function attentionLabel(p) {
  if (p.confidence === "high" && p.notify) return ["high attention", "high"];
  if (p.confidence === "high") return ["watch closely", "high"];
  return ["medium attention", "medium"];
}

function priorityCard(item) {
  const p = item.value;
  if (item.type === "standalone") {
    return `<article class="priority-card medium"><div class="priority-top"><span class="attention-pill medium">medium attention</span><span class="lifecycle">${text(p.lifecycle || "new")}</span></div><div class="agency-kicker">${text(p.canonical_agency_name || p.raw_agency_name, "Federal agency")}</div><h3>${text(p.title)}</h3><div class="brief-facts"><div><span>What happened</span><strong>An official record matched a configured watchlist condition.</strong></div><div><span>Why it matters</span><strong>${text(p.selection_reason || p.matched_value || "Exact watchlist match")}</strong></div><div><span>What to do</span><strong>Review the source and decide whether it belongs on an active watchlist.</strong></div></div><a class="primary-link" href="${esc(safeUrl(p.official_url))}" target="_blank" rel="noopener noreferrer">See the evidence ↗</a></article>`;
  }
  const [label, cls] = attentionLabel(p);
  return `<article class="priority-card ${cls}"><div class="priority-top"><span class="attention-pill ${cls}">${label}</span><span class="lifecycle">${text(p.lifecycle || "new")}</span></div><div class="agency-kicker">${text(p.canonical_agency_name || p.coordination_agency_name || "Federal activity")}</div><h3>${text(p.label || p.direction || "Coordinated federal activity")}</h3><p class="lede">${text(p.record_count, "0")} related official records moved together from ${text(p.date_start)} through ${text(p.date_end)}.</p><div class="brief-facts"><div><span>What happened</span><strong>${text(p.direction || "Related federal activity increased")}</strong></div><div><span>Why it matters</span><strong>${text(whoMayCare(p))}</strong></div><div><span>Why FedPulse noticed</span><strong>${text(whyFlagged(p))}</strong></div><div><span>What to do</span><strong>${text(actionFor(p))}</strong></div></div><details><summary>See the evidence (${(p.evidence || []).length})</summary><div class="evidence">${evidenceLinks(p.evidence)}</div></details></article>`;
}

function renderFreshness() {
  const entries = Object.entries(state.health.source_freshness || {});
  const bad = entries.filter(([, v]) => !["fresh", "running"].includes(v.status));
  $("freshness").className = `health-strip ${bad.length ? "degraded" : "fresh"}`;
  $("freshness").innerHTML = `<strong>${bad.length ? "Some source data needs attention" : "Official sources current"}</strong><span>${entries.map(([k,v]) => `${esc(k.replaceAll("_", " "))}: ${esc(v.status)}`).join(" · ") || "No source-health snapshot"}</span>`;
}

function prioritizedSignals() {
  const packages = state.packages.filter((p) => ["high", "medium"].includes(p.confidence) && p.lifecycle !== "diagnostic");
  packages.sort((a,b) => Number(Boolean(b.notify)) - Number(Boolean(a.notify)) || confidenceRank[a.confidence] - confidenceRank[b.confidence]);
  const standalone = state.standalone.filter((s) => s.notify || s.lifecycle === "new");
  return [...packages.map((value) => ({type:"package", value})), ...standalone.map((value) => ({type:"standalone", value}))];
}

function renderSignals() {
  const signals = prioritizedSignals().slice(0, 5);
  $("signal-count").textContent = String(signals.length);
  const total = Number(state.daily.total_records || 0);
  $("brief-summary").textContent = signals.length
    ? `Federal agencies published ${total.toLocaleString()} items in this snapshot. FedPulse found ${signals.length} development${signals.length === 1 ? "" : "s"} that deserve a closer look.`
    : `Federal agencies published ${total.toLocaleString()} items in this snapshot. Nothing currently clears the executive attention threshold.`;
  $("greeting").textContent = signals.length ? `${signals.length} federal development${signals.length === 1 ? "" : "s"} worth your attention.` : "Nothing requires your attention today.";
  $("signals").innerHTML = signals.length ? signals.map(priorityCard).join("") : `<div class="quiet-state hero-quiet"><strong>Nothing requires your attention today.</strong><span>FedPulse is still monitoring official federal activity. No current signal clears the evidence threshold for the executive brief.</span></div>`;
}

function renderWatching() {
  const priorityIds = new Set(prioritizedSignals().slice(0, 5).map((x) => x.value.package_id || x.value.record_id));
  const candidates = state.packages
    .filter((p) => !priorityIds.has(p.package_id) && p.lifecycle !== "diagnostic")
    .sort((a,b) => confidenceRank[a.confidence] - confidenceRank[b.confidence])
    .slice(0, 8);
  $("watch-count").textContent = String(candidates.length);
  $("watching").innerHTML = candidates.length ? candidates.map((p) => `<article class="watch-item"><div><span class="watch-agency">${text(p.canonical_agency_name || p.coordination_agency_name || "Federal agency")}</span><strong>${text(p.label || p.direction || "Developing activity")}</strong><small>${text(p.record_count,"0")} related records · ${text(p.lifecycle || "new")}</small></div><span class="trend ${p.confidence === "high" ? "up" : "steady"}">${p.confidence === "high" ? "↑ increasing" : "→ watching"}</span></article>`).join("") : `<div class="quiet-state compact"><strong>No additional developing signals.</strong><span>The current watchlist is quiet.</span></div>`;
}

function renderDaily() {
  const d = state.daily;
  $("daily-total").textContent = String(d.total_records || 0);
  const entries = Object.entries(d.document_type_counts || {}).sort((a,b) => b[1]-a[1]);
  $("daily-breakdown").innerHTML = entries.length ? entries.map(([k,v]) => `<div class="stat"><span>${esc(k.replaceAll("_", " "))}</span><strong>${text(v, "0")}</strong></div>`).join("") : `<div class="empty">No Federal Register records in this snapshot.</div>`;
}

function metricRows() {
  const out = [];
  for (const wrapper of state.metrics) for (const item of (wrapper.items || [])) if (item.alert || item.newly_elevated) out.push({...item, metric: wrapper.metric});
  return out.slice(0, 6);
}

function movementText(x) {
  if (x.z_score != null) return "Activity is materially above this agency’s recent baseline.";
  if (x.proposal_to_final_ratio != null) return "The mix of proposed and final actions is outside its recent pattern.";
  return "Activity crossed a configured FedPulse threshold.";
}

function renderMetricHighlights() {
  const rows = metricRows();
  $("metric-highlights").innerHTML = rows.length ? rows.map((x) => `<div class="movement"><div><strong>${text(x.agency || x.agency_id)}</strong><span>${text(movementText(x))}</span></div><b>${x.z_score != null ? `↑ above baseline` : x.proposal_to_final_ratio != null ? `↑ shifted` : "↑ elevated"}</b></div>`).join("") : `<div class="quiet-state compact"><strong>No agencies outside configured thresholds.</strong><span>Supporting metrics remain available below.</span></div>`;
}

function packageMatches(p) {
  const values = {
    "agency-filter": [p.canonical_agency_name, p.coordination_agency_id, ...(p.raw_agency_names || [])].join(" ").toLowerCase(),
    "direction-filter": String(p.direction || "").toLowerCase(),
    "sector-filter": packageSectors(p).join(" ").toLowerCase(),
  };
  return Object.entries(values).every(([id,value]) => { const q = ($(id).value || "").trim().toLowerCase(); return !q || value.includes(q); });
}

function renderPackages() {
  const confidence = $("confidence-filter").value;
  const lifecycle = $("lifecycle-filter").value;
  const items = state.packages.filter((p) => (!confidence || p.confidence === confidence) && (!lifecycle || (p.lifecycle || "new") === lifecycle) && packageMatches(p));
  $("package-count").textContent = String(items.length);
  $("packages").innerHTML = items.length ? items.map((p) => `<article class="card ${p.confidence === "low" ? "low-confidence" : ""}"><div class="card-top"><div><span class="badge ${esc(p.confidence || "medium")}">${text(p.confidence)}</span><h3>${text(p.label || p.canonical_agency_name)}</h3></div><span class="lifecycle">${text(p.lifecycle || "new")}</span></div><p class="meta-line">${text(p.date_start)} → ${text(p.date_end)} · ${text(p.record_count,"0")} records · ${text(p.direction)}</p><p>${text(whyFlagged(p))}</p><p class="muted">May matter to: ${text(whoMayCare(p))}</p><details><summary>Evidence (${(p.evidence || []).length})</summary><div class="evidence">${evidenceLinks(p.evidence)}</div></details></article>`).join("") : `<div class="empty">No packages match these filters.</div>`;
}

function renderStandalone() {
  $("standalone-count").textContent = String(state.standalone.length);
  $("standalone").innerHTML = state.standalone.length ? state.standalone.map((s) => `<article class="card"><div class="card-top"><h3>${text(s.canonical_agency_name || s.raw_agency_name)}</h3><span class="badge medium">watchlist</span></div><p>${text(s.title)}</p><p class="muted">${text(s.publication_date)} · ${text(s.lifecycle || "new")}</p><a class="primary-link" href="${esc(safeUrl(s.official_url))}" target="_blank" rel="noopener noreferrer">Official record ↗</a></article>`).join("") : `<div class="empty">No standalone watchlist matches.</div>`;
}

function renderMarc() {
  $("marc").innerHTML = state.marc.length ? state.marc.slice(0, 10).map((m) => `<article class="card"><div class="card-top"><h3>${text(m.subject)}</h3><span class="badge ${esc(m.confidence)}">${text(m.confidence)}</span></div><p class="muted">${text(m.last_four_week_catalog_count,"0")} records · ${text(m.distinct_cataloged_dates,"0")} dates · ${text(m.distinct_canonical_agencies,"0")} agencies</p><details><summary>Catalog evidence</summary><div class="evidence">${evidenceLinks(m.evidence, 4)}</div></details></article>`).join("") : `<div class="empty">No GPO horizon topics.</div>`;
}

function renderDiagnostics() {
  $("fr-metrics").innerHTML = state.metrics.map((m) => `<article class="card"><h3>${text((m.metric || "metric").replaceAll("_", " "))}</h3><p class="muted">${text(m.comparison_basis || m.source_cadence)}</p><div class="diagnostic-rows">${(m.items || []).slice(0,30).map((x) => `<div><span>${text(x.agency || x.agency_id || x.signal_key)}</span><strong>${x.z_score != null ? `z ${text(x.z_score)}` : x.proposal_to_final_ratio != null ? text(x.proposal_to_final_ratio) : x.alert ? "alert" : "support"}</strong></div>`).join("") || `<span class="muted">No rows.</span>`}</div></article>`).join("");
}

async function fetchPayload(name) {
  const response = await fetch(`../data/outputs/current/${name}.json`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${name}: HTTP ${response.status}`);
  return { payload: await response.json(), generation: response.headers.get("x-fedpulse-generation") || "unknown" };
}

async function load() {
  try {
    const names = ["daily_activity","packages","standalone","fr_metrics","marc_horizon","health","brief"];
    const results = await Promise.all(names.map(fetchPayload));
    for (const {payload} of results) if (payload.schema_version !== 2) throw new Error("unsupported output schema");
    const generations = new Set(results.map((x) => x.generation));
    if (generations.size !== 1) throw new Error(`mixed dashboard generations: ${[...generations].join(", ")}`);
    const generated = new Set(results.map((x) => x.payload.generated_at));
    const asOf = new Set(results.map((x) => x.payload.as_of));
    if (generated.size !== 1 || asOf.size !== 1) throw new Error("snapshot metadata is inconsistent");

    const [daily, packages, standalone, metrics, marc, health, brief] = results.map((x) => x.payload);
    state.daily = (daily.items || [])[0] || {};
    state.packages = packages.items || [];
    state.standalone = standalone.items || [];
    state.metrics = metrics.items || [];
    state.marc = marc.items || [];
    state.health = health;
    state.brief = brief;
    state.generation = results[0].generation;
    $("asof").textContent = `as of ${health.as_of || "—"}`;
    $("generation").textContent = `generation ${state.generation.slice(0, 18)}`;
    $("status").textContent = `Last checked ${health.generated_at || "—"} · ${state.packages.length} evidence packages · official sources only`;
  } catch (error) {
    $("status").textContent = `Snapshot unavailable: ${error.message}`;
    $("freshness").className = "health-strip degraded";
    $("freshness").innerHTML = `<strong>Snapshot unavailable</strong><span>${esc(error.message)}</span>`;
    return;
  }
  renderFreshness(); renderSignals(); renderWatching(); renderDaily(); renderMetricHighlights(); renderPackages(); renderStandalone(); renderMarc(); renderDiagnostics();
}

["agency-filter","direction-filter","sector-filter","confidence-filter","lifecycle-filter"].forEach((id) => $(id).addEventListener("input", renderPackages));
load();
