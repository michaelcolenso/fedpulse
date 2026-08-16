"""Detect unusually promising low-visibility federal opportunities from the local event corpus."""
from __future__ import annotations
import datetime as dt
import json, os, tempfile
from pathlib import Path

from .opportunities import _date, _haystack, _identifiers, _payload, load_profile, load_profiles, score_event


def _geo_hits(haystack: str, profile: dict) -> list[str]:
    return sorted({g for g in profile.get("geographies", []) if g.lower() in haystack})


def _history(conn, before: str):
    return conn.execute("SELECT * FROM government_events WHERE kind='contract_opportunity' AND COALESCE(event_date,'') < ? ORDER BY event_date",(before,)).fetchall()


def _historical_counts(conn,row,ids,profile):
    agency=(row["agency"] or "").strip().lower(); naics=(ids.get("naics") or [None])[0]
    haystack=_haystack(row,_payload(row)); geos=_geo_hits(haystack,profile); geo=geos[0].lower() if geos else None
    before=str(row["event_date"] or "9999-12-31"); agency_naics=combo=agency_recent=agency_prior=0; cutoff=_date(before)
    for prior in _history(conn,before):
        pids=_identifiers(conn,prior["event_id"]); pnaics=(pids.get("naics") or [None])[0]; pagency=(prior["agency"] or "").strip().lower()
        phay=_haystack(prior,_payload(prior)); pgeos=_geo_hits(phay,profile); pgeo=pgeos[0].lower() if pgeos else None
        if agency and pagency==agency and naics and pnaics==naics: agency_naics+=1
        if agency and pagency==agency and naics and pnaics==naics and geo and pgeo==geo: combo+=1
        if cutoff and agency and pagency==agency:
            pdate=_date(prior["event_date"])
            if pdate:
                age=(cutoff-pdate).days
                if 0<age<=30: agency_recent+=1
                elif 30<age<=180: agency_prior+=1
    return {"agency_naics_prior":agency_naics,"agency_naics_geo_prior":combo,"agency_recent_30d":agency_recent,"agency_prior_150d":agency_prior,"geo":geo,"naics":naics}


def hidden_gem_score(conn,row,profile,as_of: dt.date):
    ids=_identifiers(conn,row["event_id"]); base=score_event(row,ids,profile,as_of)
    if not base or base["kind"]!="contract_opportunity": return None
    stats=_historical_counts(conn,row,ids,profile); components={"base_fit":min(40,base["score"]*.28),"rarity":0,"first_combination":0,"buying_shift":0,"low_visibility_proxy":0,"competition_edge":0}; reasons=[]
    if stats["agency_naics_prior"]==0 and stats["naics"]: components["rarity"]=20; reasons.append("first observed agency + NAICS pairing")
    elif stats["agency_naics_prior"]<=2 and stats["naics"]: components["rarity"]=12; reasons.append("rare agency + NAICS pairing")
    if stats["agency_naics_geo_prior"]==0 and stats["naics"] and stats["geo"]: components["first_combination"]=18; reasons.append("first observed agency + NAICS + geography combination")
    recent=stats["agency_recent_30d"]; prior=stats["agency_prior_150d"]; monthly_prior=prior/5 if prior else 0
    if recent>=3 and (monthly_prior==0 or recent>=monthly_prior*2.5): components["buying_shift"]=14; reasons.append("agency buying activity recently accelerated")
    stage=(row["stage"] or "").lower(); haystack=_haystack(row,_payload(row))
    if any(x in stage for x in ("sources sought","presolicitation","pre-solicitation","special notice")): components["low_visibility_proxy"]=16; reasons.append("upstream notice stage")
    if "sole source" in haystack: components["competition_edge"]=12; reasons.append("limited-competition signal")
    elif any(x in haystack for x in ("small business set-aside","small business set aside","hubzone","8(a)","women-owned small business","service-disabled veteran")): components["competition_edge"]=10; reasons.append("restricted competition signal")
    score=round(sum(components.values()),1)
    if score<48 or not (components["rarity"] or components["first_combination"] or components["buying_shift"] or components["low_visibility_proxy"]): return None
    return {**base,"hidden_gem_score":score,"hidden_gem_components":components,"hidden_gem_reasons":reasons,"historical_context":stats}


def detect_hidden_gems(conn,as_of: str,profile_name: str="default",limit: int=20):
    profile=load_profile(profile_name); day=dt.date.fromisoformat(as_of); out=[]
    rows=conn.execute("SELECT * FROM government_events WHERE kind='contract_opportunity' ORDER BY COALESCE(event_date,'') DESC,last_seen DESC").fetchall()
    for row in rows:
        item=hidden_gem_score(conn,row,profile,day)
        if item: out.append(item)
    out.sort(key=lambda x:(-x["hidden_gem_score"],-x["score"],x["event_id"])); return out[:limit]


def publish_hidden_gems(conn,as_of: str,out_dir: Path,now: dt.datetime,freshness: dict|None=None):
    profiles=load_profiles(); combined={}; by_profile={}
    for name,profile in profiles.items():
        items=detect_hidden_gems(conn,as_of,name); by_profile[name]={"label":profile.get("label"),"items":items}
        for item in items:
            current=combined.setdefault(item["event_id"],{**item,"profiles":[],"profile_scores":{}}); current["profiles"].append(name); current["profile_scores"][name]=item["hidden_gem_score"]
            if item["hidden_gem_score"]>current["hidden_gem_score"]: current.update({k:v for k,v in item.items() if k not in {"profiles","profile_scores"}})
    items=sorted(combined.values(),key=lambda x:(-x["hidden_gem_score"],-x["score"]))[:30]
    if now.tzinfo is None: now=now.replace(tzinfo=dt.timezone.utc)
    payload={"schema_version":2,"generated_at":now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"as_of":as_of,"source_freshness":freshness or {},"profiles":by_profile,"items":items}
    out_dir=Path(out_dir); targets=[out_dir/"hidden_gems.json"]; current=out_dir/"current"
    if current.exists(): targets.append(current/"hidden_gems.json")
    for target in targets:
        target.parent.mkdir(parents=True,exist_ok=True); fd,tmp=tempfile.mkstemp(prefix=f".{target.name}.",suffix=".tmp",dir=target.parent)
        try:
            with os.fdopen(fd,"w",encoding="utf-8") as fh: json.dump(payload,fh,ensure_ascii=False,sort_keys=True,indent=2); fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
            os.replace(tmp,target)
        except Exception:
            try: os.unlink(tmp)
            except OSError: pass
            raise
    return payload
