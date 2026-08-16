"""Deterministic relevance ranking for FedPulse government-action events."""
from __future__ import annotations
import datetime as dt
import json, os, tempfile
from pathlib import Path
from typing import Any
CONFIG_PATH = Path(__file__).with_name("config") / "watch_profiles.json"

def load_profiles(path: Path = CONFIG_PATH) -> dict[str, Any]: return json.loads(Path(path).read_text())
def load_profile(name: str = "default", path: Path = CONFIG_PATH) -> dict[str, Any]:
    profiles=load_profiles(path)
    if name not in profiles: raise KeyError(f"unknown watch profile: {name}")
    return profiles[name]
def _date(value):
    if not value:return None
    try:return dt.date.fromisoformat(str(value)[:10])
    except ValueError:return None
def _row_value(row,key,default=None):
    try:return row[key]
    except (KeyError,IndexError):return default
def _payload(row):
    try:return json.loads((_row_value(row,"payload_json") or "{}"))
    except (TypeError,json.JSONDecodeError):return {}
def _haystack(row,payload):return " ".join(str(x or "") for x in (_row_value(row,"title"),_row_value(row,"agency"),_row_value(row,"stage"),json.dumps(payload,ensure_ascii=False))).lower()
def _identifiers(conn,event_id):
    out={}
    for row in conn.execute("SELECT namespace,value FROM government_identifiers WHERE event_id=?",(event_id,)):out.setdefault(row["namespace"],[]).append(row["value"])
    return out
def _deadline(payload):
    row=payload.get("row") if isinstance(payload.get("row"),dict) else payload
    fields=payload.get("fields") if isinstance(payload.get("fields"),dict) else {}
    for source in (row,fields,payload):
        for key in ("ResponseDeadLine","response_deadline","CloseDate","closedate","close_date","closedate","applicationduedate"):
            parsed=_date(source.get(key) if isinstance(source,dict) else None)
            if parsed:return parsed
    return None
def lane_for(kind: str,days_to_close: int|None)->str:
    if kind in {"contract_opportunity","funding_opportunity"} and (days_to_close is None or days_to_close>=0):return "act_now"
    if kind=="federal_award_action":return "market_intelligence"
    if kind in {"stakeholder_meeting","legislative_update"}:return "policy_signals"
    return "market_intelligence"
def _early_stage(stage,kind):
    s=(stage or "").lower()
    if "forecast" in s:return 20,"forecast-stage signal"
    if "sources sought" in s:return 20,"sources-sought signal"
    if "presolicitation" in s or "pre-solicitation" in s:return 17,"presolicitation signal"
    if "special notice" in s:return 11,"special-notice signal"
    if "intent to sole source" in s or "sole source" in s:return 9,"limited-competition signal"
    if kind=="stakeholder_meeting":return 14,"upstream OIRA activity"
    if kind=="legislative_update":return 10,"upstream legislative activity"
    return 0,None
def _competition_signal(haystack):
    if "total small business set-aside" in haystack or "total small business set aside" in haystack:return 10,"small-business set-aside"
    if "8(a)" in haystack or "hubzone" in haystack or "service-disabled veteran" in haystack or "women-owned small business" in haystack:return 9,"restricted competition"
    if "set-aside" in haystack or "set aside" in haystack:return 6,"set-aside opportunity"
    return 0,None
def _first_seen_bonus(row,as_of):
    first=_date(_row_value(row,"first_seen"))
    if not first:return 0,None
    age=(as_of-first).days
    if age<0:return 0,None
    if age==0:return 18,"newly discovered today"
    if age==1:return 14,"discovered yesterday"
    if age<=3:return 8,"newly discovered"
    return 0,None
def score_event(row,identifiers,profile,as_of):
    payload=_payload(row);haystack=_haystack(row,payload);event_date=_date(_row_value(row,"event_date"));lookback=int(profile.get("lookback_days",7))
    if not event_date or (as_of-event_date).days<0 or (as_of-event_date).days>lookback:return None
    components={"freshness":max(0,28-(as_of-event_date).days*4),"novelty":0,"relevance":0,"specificity":0,"urgency":0,"magnitude":0,"early_signal":0,"competition":0,"actionability":0}; reasons=[]
    novelty,why=_first_seen_bonus(row,as_of);components["novelty"]=novelty
    if why:reasons.append(why)
    keyword_hits=[x for x in profile.get("keywords",[]) if x.lower() in haystack]
    if keyword_hits:components["relevance"]+=min(26,8+len(set(keyword_hits))*3);reasons.append("topic: "+", ".join(sorted(set(keyword_hits))[:4]))
    geo_hits=[x for x in profile.get("geographies",[]) if x.lower() in haystack]
    if geo_hits:components["relevance"]+=24;reasons.append("geography: "+", ".join(sorted(set(geo_hits))[:3]))
    naics=set(identifiers.get("naics",[]));hits=sorted(naics & set(str(x) for x in profile.get("naics",[])))
    if hits:components["relevance"]+=26;reasons.append("NAICS: "+", ".join(hits[:3]))
    agency=str(_row_value(row,"agency") or "");agency_hits=[x for x in profile.get("agencies",[]) if x.lower() in agency.lower()]
    if agency_hits:components["relevance"]+=9;reasons.append("agency: "+agency_hits[0])
    dimensions=sum(bool(x) for x in (keyword_hits,geo_hits,hits,agency_hits))
    if dimensions>=2:components["specificity"]=(dimensions-1)*7;reasons.append(f"{dimensions}-factor profile match")
    amount=float(_row_value(row,"amount")) if _row_value(row,"amount") is not None else None
    if amount is not None:
        if abs(amount)>=float(profile.get("high_value_amount",500000)):components["magnitude"]=10;reasons.append(f"value: ${abs(amount):,.0f}")
        elif abs(amount)>=float(profile.get("minimum_amount",25000)):components["magnitude"]=5;reasons.append(f"value: ${abs(amount):,.0f}")
    deadline=_deadline(payload);days=(deadline-as_of).days if deadline else None
    if days is not None:
        if 0<=days<=int(profile.get("closing_soon_days",10)):components["urgency"]=12;reasons.append(f"closes in {days} days")
        elif 11<=days<=45:components["urgency"]=6;reasons.append(f"useful runway: {days} days")
        elif days<0:return None
    kind=str(_row_value(row,"kind") or "");early,early_reason=_early_stage(_row_value(row,"stage"),kind);components["early_signal"]=early
    if early_reason:reasons.append(early_reason)
    comp,comp_reason=_competition_signal(haystack);components["competition"]=comp
    if comp_reason:reasons.append(comp_reason)
    if kind in {"contract_opportunity","funding_opportunity"}:components["actionability"]=8
    elif kind=="federal_award_action" and amount:components["actionability"]=4
    if not (keyword_hits or geo_hits or hits or agency_hits):return None
    score=sum(components.values()); edge="standard"
    if components["early_signal"]>=17 and dimensions>=2:edge="early"
    elif components["novelty"]>=14 and dimensions>=2:edge="new"
    elif components["specificity"]>=14:edge="high-fit"
    return {"event_id":_row_value(row,"event_id"),"source":_row_value(row,"source"),"kind":kind,"lane":lane_for(kind,days),"stage":_row_value(row,"stage"),"title":_row_value(row,"title"),"agency":_row_value(row,"agency"),"event_date":_row_value(row,"event_date"),"amount":amount,"currency":_row_value(row,"currency"),"official_url":_row_value(row,"official_url"),"score":round(score,1),"score_components":components,"edge":edge,"reasons":reasons,"days_to_close":days,"identifiers":identifiers}
def rank_opportunities(conn,as_of,profile_name="default",limit=30):
    profile=load_profile(profile_name);today=dt.date.fromisoformat(as_of);ranked=[]
    rows=conn.execute("SELECT * FROM government_events WHERE kind IN ('contract_opportunity','funding_opportunity','federal_award_action','stakeholder_meeting','legislative_update') ORDER BY COALESCE(event_date,'') DESC,last_seen DESC").fetchall()
    for row in rows:
        item=score_event(row,_identifiers(conn,row["event_id"]),profile,today)
        if item:ranked.append(item)
    ranked.sort(key=lambda x:(0 if x["edge"]=="early" else 1 if x["edge"]=="new" else 2,-x["score"],x.get("days_to_close") if x.get("days_to_close") is not None else 9999,x["event_id"]));return ranked[:limit]
def rank_all_profiles(conn,as_of,limit=30):
    profiles=load_profiles();by_profile={name:rank_opportunities(conn,as_of,name,limit) for name in profiles};combined={}
    for name,items in by_profile.items():
        for item in items:
            current=combined.setdefault(item["event_id"],{**item,"profiles":[],"profile_scores":{}});current["profiles"].append(name);current["profile_scores"][name]=item["score"]
            if item["score"]>current["score"]:current.update({k:v for k,v in item.items() if k not in {"profiles","profile_scores"}})
    items=list(combined.values());items.sort(key=lambda x:(0 if x["edge"]=="early" else 1 if x["edge"]=="new" else 2,-x["score"]));lanes={key:[x for x in items if x["lane"]==key] for key in ("act_now","market_intelligence","policy_signals")};return by_profile,lanes,items[:limit]
def publish_opportunities(conn,as_of,out_dir,now,*,profile_name="default",freshness=None):
    if now.tzinfo is None:now=now.replace(tzinfo=dt.timezone.utc)
    by_profile,lanes,items=rank_all_profiles(conn,as_of);profiles=load_profiles();payload={"schema_version":2,"generated_at":now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"generated_at_timezone":"UTC","as_of":as_of,"as_of_timezone":"America/New_York","source_freshness":freshness or {},"profile":{"name":"all","label":"All watch profiles"},"profiles":{name:{"label":profiles[name].get("label"),"items":vals} for name,vals in by_profile.items()},"lanes":lanes,"items":items}
    out_dir=Path(out_dir);targets=[out_dir/"opportunities_today.json"];current=out_dir/"current"
    if current.exists():targets.append(current/"opportunities_today.json")
    for target in targets:
        target.parent.mkdir(parents=True,exist_ok=True);fd,tmp=tempfile.mkstemp(prefix=f".{target.name}.",suffix=".tmp",dir=target.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as fh:json.dump(payload,fh,ensure_ascii=False,sort_keys=True,indent=2);fh.write("\n");fh.flush();os.fsync(fh.fileno())
            os.replace(tmp,target)
        except Exception:
            try:os.unlink(tmp)
            except OSError:pass
            raise
    return payload
