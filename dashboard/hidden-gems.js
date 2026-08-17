"use strict";
(() => {
  const esc=(v)=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const safeUrl=(v)=>/^https:\/\//i.test(String(v??""))?String(v):"#";
  function card(item){
    const reasons=(item.hidden_gem_reasons||[]).slice(0,5);
    const profiles=(item.profiles||[]).map(x=>`<span class="profile-chip">${esc(x.replaceAll("_"," "))}</span>`).join("");
    const ctx=item.historical_context||{};
    const rarity=[];
    if(Number(ctx.agency_naics_prior??0)===0)rarity.push("first agency + NAICS match");
    if(Number(ctx.agency_naics_geo_prior??0)===0)rarity.push("first agency + NAICS + geography match");
    return `<article class="intel-card gem-card">
      <div class="intel-top"><div><div class="card-flags"><span class="signal-chip early">hidden gem</span><span class="type-chip">${esc(item.stage||"opportunity")}</span></div><h3>${esc(item.title||"Federal opportunity")}</h3><p class="intel-meta">${esc(item.agency||"Federal agency")} · ${esc(item.event_date||"")}</p></div><div class="gem-score"><small>gem</small><strong>${esc(item.hidden_gem_score??"—")}</strong></div></div>
      <div class="profile-row">${profiles}</div>
      <div class="analysis-note"><div class="mini-label">Why it stands out</div>${reasons.length?`<ul>${reasons.map(x=>`<li>${esc(x)}</li>`).join("")}</ul>`:"<p>Unusual relative to FedPulse history.</p>"}</div>
      ${(rarity.length||ctx.agency_naics_prior!=null)?`<p class="why-line"><b>Historical context:</b> ${esc(rarity.join(" · ")||`${ctx.agency_naics_prior??0} prior agency + NAICS matches`)}</p>`:""}
      <div class="card-actions"><a class="primary-link" href="${esc(safeUrl(item.official_url))}" target="_blank" rel="noopener noreferrer">Open official record ↗</a><details><summary>Gem score</summary><div class="diagnostic-rows">${Object.entries(item.hidden_gem_components||{}).filter(([,v])=>Number(v)>0).map(([k,v])=>`<div><span>${esc(k.replaceAll("_"," "))}</span><strong>+${esc(v)}</strong></div>`).join("")}</div></details></div>
    </article>`;
  }
  async function load(){
    const list=document.getElementById("hidden-gem-list"),count=document.getElementById("hidden-gem-count");
    if(!list||!count)return;
    try{
      const response=await fetch("../data/outputs/current/hidden_gems.json",{cache:"no-store"});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const payload=await response.json(),items=payload.items||[];
      count.textContent=String(items.length);
      list.className="intel-list";
      list.innerHTML=items.length?items.slice(0,12).map(card).join(""):`<div class="quiet-state compact"><strong>No hidden gems cleared the threshold.</strong><span>FedPulse does not manufacture signal.</span></div>`;
    }catch(error){count.textContent="—";list.innerHTML=`<div class="empty">Hidden-gem feed unavailable: ${esc(error.message)}</div>`;}
  }
  load();
})();