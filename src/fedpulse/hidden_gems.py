"""Detect unusually promising low-visibility federal opportunities from the local event corpus."""
from __future__ import annotations
import bisect
import datetime as dt
import json, os, tempfile
from collections import defaultdict
from pathlib import Path

from .opportunities import _date, _haystack, _payload, load_profile, load_profiles, score_event


def _geo_hits(haystack: str, profile: dict) -> list[str]:
    return sorted({g for g in profile.get("geographies", []) if g.lower() in haystack})


def _all_identifiers(conn):
    out=defaultdict(lambda: defaultdict(list))
    for row in conn.execute("SELECT event_id,namespace,value FROM government_identifiers"):
        out[row["event_id"]][row["namespace"]].append(row["value"])
    return out


def _history_stats(agency,naics,geo,event_date,agency_naics,agency_naics_geo,agency_dates):
    dates=agency_dates.get(agency,[]); ordinal=event_date.toordinal()
    recent=bisect.bisect_left(dates,ordinal-30); prior_start=bisect.bisect_left(dates,ordinal-180)
    return {
        "agency_naics_prior":agency_naics.get((agency,naics),0) if naics else 0,
        "agency_naics_geo_prior":agency_naics_geo.get((agency,naics,geo),0) if naics and geo else 0,
        "agency_recent_30d":len(dates)-recent,
        "agency_prior_150d":recent-prior_start,
        "geo":geo,"naics":naics,
    }


def _build_gem(base,row,stats):
    components={"base_fit":min(40,base["score"]*.28),"rarity":0,"first_combination":0,"buying_shift":0,"low_visibility_proxy":0,"competition_edge":0}; reasons=[]
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
    profile=load_profile(profile_name); day=dt.date.fromisoformat(as_of); lookback=int(profile.get("lookback_days",7)); ids_by_event=_all_identifiers(conn)
    rows=conn.execute("SELECT * FROM government_events WHERE kind='contract_opportunity' ORDER BY COALESCE(event_date,''),event_id").fetchall()
    agency_naics=defaultdict(int); agency_naics_geo=defaultdict(int); agency_dates=defaultdict(list); out=[]
    for row in rows:
        event_date=_date(row["event_date"])
        if not event_date: continue
        ids=ids_by_event.get(row["event_id"],{}); naics=(ids.get("naics") or [None])[0]; agency=(row["agency"] or "").strip().lower(); haystack=_haystack(row,_payload(row)); geos=_geo_hits(haystack,profile); geo=geos[0].lower() if geos else None
        stats=_history_stats(agency,naics,geo,event_date,agency_naics,agency_naics_geo,agency_dates)
        age=(day-event_date).days
        if 0<=age<=lookback:
            base=score_event(row,ids,profile,day)
            if base:
                gem=_build_gem(base,row,stats)
                if gem: out.append(gem)
        if agency:
            agency_dates[agency].append(event_date.toordinal())
            if naics: agency_naics[(agency,naics)]+=1
            if naics and geo: agency_naics_geo[(agency,naics,geo)]+=1
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
