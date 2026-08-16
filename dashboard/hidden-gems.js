"use strict";
(() => {
  const esc=(v)=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const safeUrl=(v)=>/^https:\/\//i.test(String(v??""))?String(v):"#";
  function card(item){
    const reasons=(item.hidden_gem_reasons||[]).map(x=>`<li>${esc(x)}</li>`).join("");
    const profiles=(item.profiles||[]).map(x=>`<span class="badge">${esc(x.replaceAll("_"," "))}</span>`).join(" ");
    const ctx=item.historical_context||{};
    return `<article class="card opportunity-card"><div class="card-top"><div><span class="badge high">gem ${esc(item.hidden_gem_score)}</span><h3>${esc(item.title||"Federal opportunity")}</h3></div><span class="lifecycle">${esc(item.stage||"opportunity")}</span></div><p class="meta-line">${esc(item.agency||"Federal agency")} · ${esc(item.event_date||"")}</p><div>${profiles}</div><p class="muted">Historical context: ${esc(ctx.agency_naics_prior??0)} prior agency+NAICS matches · ${esc(ctx.agency_naics_geo_prior??0)} prior agency+NAICS+geography matches.</p><ul class="muted">${reasons}</ul><details><summary>Why this scored as a hidden gem</summary><pre>${esc(JSON.stringify(item.hidden_gem_components||{},null,2))}</pre></details><a class="primary-link" href="${esc(safeUrl(item.official_url))}" target="_blank" rel="noopener noreferrer">Official record ↗</a></article>`;
  }
  async function load(){const list=document.getElementById("hidden-gem-list"),count=document.getElementById("hidden-gem-count"); if(!list||!count)return; try{const response=await fetch("../data/outputs/current/hidden_gems.json",{cache:"no-store"}); if(!response.ok)throw new Error(`HTTP ${response.status}`); const payload=await response.json(),items=payload.items||[]; count.textContent=String(items.length); list.innerHTML=items.length?items.slice(0,12).map(card).join(""):`<div class="quiet-state compact"><strong>No hidden gems cleared the threshold.</strong><span>That is a valid result; FedPulse will not manufacture obscurity.</span></div>`;}catch(error){count.textContent="—";list.innerHTML=`<div class="empty">Hidden-gem feed unavailable: ${esc(error.message)}</div>`;}}
  load();
})();
