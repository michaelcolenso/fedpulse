"use strict";

(() => {
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const safeUrl = (value) => /^https:\/\//i.test(String(value ?? "")) ? String(value) : "#";
  const money = (value) => value == null ? "" : new Intl.NumberFormat("en-US", {style:"currency",currency:"USD",maximumFractionDigits:0}).format(value);
  const kindLabel = (kind) => ({contract_opportunity:"contract",funding_opportunity:"funding",federal_award_action:"award activity",stakeholder_meeting:"OIRA meeting",legislative_update:"legislation"}[kind] || kind || "federal activity");

  function card(item) {
    const close = item.days_to_close == null ? "" : `<span>${item.days_to_close === 0 ? "closes today" : `closes in ${item.days_to_close}d`}</span>`;
    const amount = item.amount == null ? "" : `<span>${esc(money(item.amount))}</span>`;
    const reasons = (item.reasons || []).map((x) => `<li>${esc(x)}</li>`).join("");
    return `<article class="card opportunity-card"><div class="card-top"><div><span class="badge high">score ${esc(item.score)}</span><h3>${esc(item.title || "Federal opportunity")}</h3></div><span class="lifecycle">${esc(kindLabel(item.kind))}</span></div><p class="meta-line">${esc(item.agency || "Federal agency")} · ${esc(item.event_date || "")}</p><p class="meta-line">${amount}${close}</p><ul class="muted">${reasons}</ul><a class="primary-link" href="${esc(safeUrl(item.official_url))}" target="_blank" rel="noopener noreferrer">Official record ↗</a></article>`;
  }

  async function load() {
    const list = document.getElementById("opportunity-list");
    const count = document.getElementById("opportunity-count");
    if (!list || !count) return;
    try {
      const response = await fetch("../data/outputs/current/opportunities_today.json", {cache:"no-store"});
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const items = payload.items || [];
      count.textContent = String(items.length);
      list.innerHTML = items.length ? items.slice(0, 12).map(card).join("") : `<div class="quiet-state compact"><strong>No current matches.</strong><span>The watch profile found no fresh federal activity worth surfacing.</span></div>`;
    } catch (error) {
      count.textContent = "—";
      list.innerHTML = `<div class="empty">Opportunities feed unavailable: ${esc(error.message)}</div>`;
    }
  }

  load();
})();
