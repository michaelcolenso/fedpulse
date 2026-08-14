"""Schema-v2 atomic snapshots and evidence-first daily brief."""
from __future__ import annotations
import datetime as dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from . import db
from .health import source_freshness
from .horizon import compute_marc_horizon
from .lifecycle import update_signal_state
from .metrics_v2 import compute_fr_activity, compute_level_shifts, compute_pipeline_metrics
from .normalize_agencies import normalize_all
from .packages import detect_packages, persist_package_versions
from .watchlist import detect_standalone

SCHEMA_VERSION=2

def _base(as_of: str, now: dt.datetime, items: list | None = None, freshness: dict | None = None) -> dict:
    if now.tzinfo is None: now=now.replace(tzinfo=dt.timezone.utc)
    return {"schema_version":SCHEMA_VERSION,"generated_at":now.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"generated_at_timezone":"UTC","as_of":as_of,"as_of_timezone":"America/New_York","source_freshness":freshness or {},"items":items or []}

def atomic_write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); fd,name=tempfile.mkstemp(prefix=f".{path.name}.",suffix=".tmp",dir=path.parent)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as fh:
            json.dump(payload,fh,ensure_ascii=False,sort_keys=True,indent=2); fh.write("\n"); fh.flush(); os.fsync(fh.fileno())
        os.replace(name,path)
    except Exception:
        try: os.unlink(name)
        except OSError: pass
        raise

def _daily(conn, as_of: str) -> dict:
    rows=conn.execute("select doc_type,canonical_agency_id,canonical_agency_name,agency from records where source='fr' and publication_date=? order by id",(as_of,)).fetchall(); counts={}
    agencies={}
    for r in rows:
        typ=r["doc_type"] or "unknown"; counts[typ]=counts.get(typ,0)+1; key=r["canonical_agency_id"] or r["agency"] or "unmapped"; agencies[key]=agencies.get(key,0)+1
    return {"date":as_of,"total_records":len(rows),"document_type_counts":counts,"agency_counts":agencies}

def build_brief(payloads: Mapping[str, dict]) -> dict:
    health=payloads.get("health",{}); packages=[p for p in payloads.get("packages",{}).get("items",[]) if p.get("confidence") in {"high","medium"} and p.get("lifecycle","new") != "resolved"]; standalone=payloads.get("standalone",{}).get("items",[]); daily=payloads.get("daily_activity",{}).get("items",[]); metrics=payloads.get("fr_metrics",{}).get("items",[]); horizon=payloads.get("marc_horizon",{}).get("items",[])
    sections=[]
    warnings=[{"component":k,"status":v.get("status"),"detail":v.get("detail")} for k,v in health.get("source_freshness",{}).items() if v.get("status") not in {"fresh","running"}]
    if warnings: sections.append({"section":"health","items":warnings})
    sections.append({"section":"daily_activity","items":daily})
    if packages: sections.append({"section":"high_medium_packages","items":packages})
    if standalone: sections.append({"section":"standalone_watchlist","items":standalone})
    if metrics: sections.append({"section":"supporting_metrics","items":metrics})
    if horizon: sections.append({"section":"marc_horizon","items":horizon})
    return {"schema_version":2,"generated_at":payloads.get("health",{}).get("generated_at"),"generated_at_timezone":"UTC","as_of":payloads.get("health",{}).get("as_of"),"as_of_timezone":"America/New_York","source_freshness":health.get("source_freshness",{}),"items":sections}

def render_text_brief(brief: Mapping[str, Any]) -> str:
    lines=[f"FEDPULSE — {brief.get('as_of') or 'unknown'}"]
    for section in brief.get("items",[]):
        name=section.get("section","").upper().replace("_"," "); lines.append(f"\n{name}:")
        for item in section.get("items",[]):
            if section.get("section")=="daily_activity": lines.append(f"  TODAY: {item.get('total_records',0)} FR records · {item.get('document_type_counts',{})}")
            elif item.get("label"): lines.append(f"  • {item['label']} — {item.get('confidence','')}; evidence: {len(item.get('evidence',[]))} records")
            elif item.get("title"): lines.append(f"  • {item.get('title')} — {item.get('official_url','')}")
            else: lines.append(f"  • {item}")
    return "\n".join(lines)+"\n"

def build_v2_outputs(conn, as_of: str, out_dir: Path, now: dt.datetime | None = None) -> dict[str, dict]:
    now=now or dt.datetime.now(dt.timezone.utc); out_dir=Path(out_dir); normalize_all(conn); freshness=source_freshness(conn,now)
    packages=persist_package_versions(conn,detect_packages(conn,as_of),now.isoformat().replace("+00:00","Z"))
    standalone=detect_standalone(conn,as_of); activity=_daily(conn,as_of); fr_activity=compute_fr_activity(conn,as_of); level=compute_level_shifts(conn,as_of); pipe=compute_pipeline_metrics(conn,as_of); horizon=compute_marc_horizon(conn,as_of)
    payloads={"daily_activity":_base(as_of,now,[activity],freshness),"packages":_base(as_of,now,packages,freshness),"standalone":_base(as_of,now,standalone,freshness),"fr_metrics":_base(as_of,now,[fr_activity,level,pipe],freshness),"marc_horizon":{**horizon,"source_freshness":freshness},"health":_base(as_of,now,[{"component":k,**v} for k,v in freshness.items()],freshness)}
    payloads["brief"]=build_brief(payloads)
    for name,payload in payloads.items(): atomic_write_json(out_dir/f"{name}.json",payload)
    return payloads
