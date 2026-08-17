"use strict";
(() => {
  const esc=(v)=>String(v??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const safeUrl=(v)=>/^https:\/\//i.test(String(v??""))?String(v):"#";
  const money=(v,c="USD")=>v==null?"":new Intl.NumberFormat("en-US",{style:"currency",currency:c||"USD",maximumFractionDigits:0}).format(v);
  const kindLabel=(k)=>({contract_opportunity:"contract",funding_opportunity:"funding",federal_award_action:"award",stakeholder_meeting:"OIRA meeting",legislative_update:"legislation"}[k]||k||"federal activity");
  const edgeLabel=(e)=>({early:"early signal",new:"new","high-fit":"high fit",standard:"matched"}[e]||"matched");
  const laneMeta={act_now:["Act now","Open contracts and funding where action can still affect the outcome."],market_intelligence:["Market intelligence","Awards and activity showing where federal demand and money are moving."],policy_signals:["Policy signals","Upstream legislative and regulatory activity worth watching."]};

  function evidenceValue(row){
    if(row.type==="amount") return money(row.value,row.currency);
    return String(row.value??"");
  }
  function evidenceBlock(item){
    const rows=(item.evidence_summary||[]).slice(0,6);
    if(!rows.length)return "";
    return `<div class="evidence-facts"><div class="mini-label">Evidence</div><div class="fact-grid">${rows.map(row=>`<div class="fact"><span>${esc(row.label)}</span><strong>${esc(evidenceValue(row))}</strong></div>`).join("")}</div></div>`;
  }
  function analysisBlock(item){
    const ai=item.ai||{};
    if(!ai.enabled)return `<div class="analysis-note"><div class="mini-label">Analysis</div><p>Ranked from deterministic evidence plus semantic match. No generative model influenced this result.</p></div>`;
    const analyst=ai.analyst||{};
    const reasons=(analyst.reasons||[]).slice(0,3).map(x=>`<li>${esc(x.text)}</li>`).join("");
    const skeptic=ai.skeptic;
    const skepticText=skeptic?`<span class="skeptic ${skeptic.verdict==='pass'?'pass':''}">Skeptic: ${esc(skeptic.verdict)}</span>`:"";
    return `<div class="analysis-note ai"><div class="analysis-head"><div class="mini-label">FedPulse analysis</div>${skepticText}</div><div class="judgments"><span>Fit <b>${esc(analyst.commercial_fit||"—")}</b></span><span>Action <b>${esc(analyst.actionability||"—")}</b></span><span>Evidence <b>${esc(analyst.evidence_sufficiency||"—")}</b></span></div>${reasons?`<ul>${reasons}</ul>`:""}</div>`;
  }
  function relatedBlock(item){
    const related=(item.related_actions||[]).slice(0,4);
    if(!related.length)return "";
    return `<details class="related"><summary>Related official actions · ${related.length}</summary><div class="timeline">${related.map(x=>`<a href="${esc(safeUrl(x.official_url))}" target="_blank" rel="noopener noreferrer"><time>${esc(x.event_date||"—")}</time><span><b>${esc(kindLabel(x.kind))}</b>${esc(x.title||x.stage||"Related action")}</span></a>`).join("")}</div></details>`;
  }
  function rankingMeta(item){
    const semantic=Number(item.semantic_score||0);
    const hybrid=Number(item.hybrid_score??item.score??0);
    const base=Number(item.score||0);
    const aiAdj=Number(item.ai_adjustment||0);
    return `<div class="ranking-meta"><span>evidence ${esc(base.toFixed(0))}</span><span>semantic ${esc(semantic.toFixed(2))}</span>${aiAdj?`<span>AI ${aiAdj>0?"+":""}${esc(aiAdj)}</span>`:""}<strong>${esc(hybrid.toFixed(0))}</strong></div>`;
  }
  function card(item){
    const profiles=(item.profiles||[]).map(x=>`<span class="profile-chip">${esc(x.replaceAll("_"," "))}</span>`).join("");
    const close=item.days_to_close==null?"":item.days_to_close===0?"Closes today":`${item.days_to_close} days left`;
    const amount=item.amount==null?"":money(item.amount,item.currency);
    const secondary=[item.agency,item.event_date,amount,close].filter(Boolean).map(esc).join(" · ");
    const reasons=(item.reasons||[]).filter(x=>!x.startsWith("geography:")&&!x.startsWith("agency:")).slice(0,3);
    return `<article class="intel-card">
      <div class="intel-top"><div><div class="card-flags"><span class="signal-chip ${esc(item.edge||'standard')}">${esc(edgeLabel(item.edge))}</span><span class="type-chip">${esc(kindLabel(item.kind))}</span></div><h3>${esc(item.title||"Federal opportunity")}</h3><p class="intel-meta">${secondary}</p></div>${rankingMeta(item)}</div>
      <div class="profile-row">${profiles}</div>
      ${evidenceBlock(item)}
      ${analysisBlock(item)}
      ${reasons.length?`<p class="why-line"><b>Why now:</b> ${reasons.map(esc).join(" · ")}</p>`:""}
      ${relatedBlock(item)}
      <div class="card-actions"><a class="primary-link" href="${esc(safeUrl(item.official_url))}" target="_blank" rel="noopener noreferrer">Open official record ↗</a><details><summary>Scoring</summary><div class="diagnostic-rows">${Object.entries(item.score_components||{}).filter(([,v])=>Number(v)>0).map(([k,v])=>`<div><span>${esc(k.replaceAll("_"," "))}</span><strong>+${esc(v)}</strong></div>`).join("")}</div></details></div>
    </article>`;
  }
  function lane(key,items){
    const [title,desc]=laneMeta[key];
    return `<section class="opportunity-lane"><div class="lane-head"><div><div class="eyebrow">${esc(key.replaceAll("_"," "))}</div><h3>${esc(title)}</h3><p>${esc(desc)}</p></div><span class="count small">${items.length}</span></div><div class="intel-list">${items.length?items.slice(0,8).map(card).join(""):`<div class="quiet-state compact"><strong>Nothing strong enough to show.</strong><span>FedPulse leaves weak signals out.</span></div>`}</div></section>`;
  }
  async function load(){
    const list=document.getElementById("opportunity-list"),count=document.getElementById("opportunity-count"),mode=document.getElementById("ranking-mode");
    if(!list||!count)return;
    try{
      const response=await fetch("../data/outputs/current/opportunities_today.json",{cache:"no-store"});
      if(!response.ok)throw new Error(`HTTP ${response.status}`);
      const payload=await response.json(),lanes=payload.lanes||{},ranking=payload.ranking||{};
      count.textContent=String((payload.items||[]).length);
      if(mode){
        const text=ranking.ai_enabled?"Evidence + semantic + AI analyst/skeptic":"Evidence + semantic ranking";
        mode.textContent=text;
        mode.title=ranking.ai_enabled?"Generative analysis is evidence-bound and separately verified.":"No generative model influenced this ranking.";
      }
      list.innerHTML=["act_now","market_intelligence","policy_signals"].map(k=>lane(k,lanes[k]||[])).join("");
    }catch(error){count.textContent="—";list.innerHTML=`<div class="empty">Opportunities feed unavailable: ${esc(error.message)}</div>`;}
  }
  load();
})();