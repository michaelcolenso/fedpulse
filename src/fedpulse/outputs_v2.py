"""Schema-v2 atomic snapshots and evidence-first daily brief."""
from __future__ import annotations
import datetime as dt
import json
import os
import tempfile
import shutil
import uuid
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
OUTPUT_NAMES=("daily_activity","packages","standalone","fr_metrics","marc_horizon","health","brief")

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

def validate_snapshot(payloads: Mapping[str, Mapping[str, Any]]) -> None:
    missing=set(OUTPUT_NAMES)-set(payloads)
    if missing: raise ValueError(f"snapshot missing outputs: {sorted(missing)}")
    expected_as_of=payloads["health"].get("as_of"); expected_generated=payloads["health"].get("generated_at")
    for name in OUTPUT_NAMES:
        payload=payloads[name]
        if payload.get("schema_version") != 2: raise ValueError(f"{name} has unsupported schema_version")
        if payload.get("as_of") != expected_as_of: raise ValueError(f"{name} has inconsistent as_of")
        if payload.get("generated_at") != expected_generated: raise ValueError(f"{name} has inconsistent generated_at")
        if not isinstance(payload.get("source_freshness"),dict): raise ValueError(f"{name} is missing source_freshness")
    for package in payloads["packages"].get("items",[]):
        if not package.get("taxonomy_versions"): raise ValueError("package missing taxonomy_versions")
        for evidence in package.get("evidence",[]):
            metadata=evidence.get("metadata")
            if not evidence.get("record_id") or not isinstance(metadata,dict) or not metadata.get("taxonomy_versions"): raise ValueError("package evidence is incomplete")
            if not any(metadata.get(key) for key in ("topics","matched_phrases","coverage_tags")): raise ValueError("package evidence has no exact matched value")
            url=evidence.get("official_url")
            if url and not str(url).startswith(("https://","http://")): raise ValueError("package evidence URL is unsafe")

def _stage_snapshot(out_dir: Path, payloads: Mapping[str, Mapping[str, Any]]) -> Path:
    validate_snapshot(payloads)
    out_dir=Path(out_dir); generations=out_dir/".generations"; generations.mkdir(parents=True,exist_ok=True)
    generation_id=f"{payloads['health'].get('generated_at','generation').replace(':','').replace('-','')}-{uuid.uuid4().hex[:8]}"
    staging=generations/f".{generation_id}.tmp"; final=generations/generation_id
    staging.mkdir()
    try:
        for name in OUTPUT_NAMES: atomic_write_json(staging/f"{name}.json",payloads[name])
        os.replace(staging,final)
        return final
    except Exception:
        shutil.rmtree(staging,ignore_errors=True)
        raise

def _activate_snapshot(out_dir: Path, generation: Path) -> None:
    out_dir=Path(out_dir); relative=generation.relative_to(out_dir)
    current_tmp=out_dir/f".current.{uuid.uuid4().hex}.tmp"
    os.symlink(relative,current_tmp); os.replace(current_tmp,out_dir/"current")
    for name in OUTPUT_NAMES:
        link_tmp=out_dir/f".{name}.{uuid.uuid4().hex}.tmp"
        os.symlink(Path("current")/f"{name}.json",link_tmp)
        os.replace(link_tmp,out_dir/f"{name}.json")
    fd=os.open(out_dir,os.O_RDONLY)
    try: os.fsync(fd)
    finally: os.close(fd)
    completed=sorted((out_dir/".generations").iterdir(),key=lambda path:path.stat().st_mtime,reverse=True)
    for obsolete in [path for path in completed if path.is_dir() and not path.name.startswith(".")][3:]:
        shutil.rmtree(obsolete,ignore_errors=True)

def publish_snapshot(out_dir: Path, payloads: Mapping[str, Mapping[str, Any]]) -> None:
    generation=_stage_snapshot(Path(out_dir),payloads)
    _activate_snapshot(Path(out_dir),generation)

def _daily(conn, as_of: str) -> dict:
    rows=conn.execute("select doc_type,canonical_agency_id,canonical_agency_name,agency from records where source='fr' and publication_date=? order by id",(as_of,)).fetchall(); counts={}
    agencies={}
    for r in rows:
        typ=r["doc_type"] or "unknown"; counts[typ]=counts.get(typ,0)+1; key=r["canonical_agency_id"] or r["agency"] or "unmapped"; agencies[key]=agencies.get(key,0)+1
    return {"date":as_of,"total_records":len(rows),"document_type_counts":counts,"agency_counts":agencies}

def build_brief(payloads: Mapping[str, dict]) -> dict:
    health=payloads.get("health",{})
    packages=[p for p in payloads.get("packages",{}).get("items",[]) if p.get("confidence") in {"high","medium"} and p.get("notify")]
    standalone=[p for p in payloads.get("standalone",{}).get("items",[]) if p.get("notify")]
    daily=payloads.get("daily_activity",{}).get("items",[])
    metrics=[]
    for wrapper in payloads.get("fr_metrics",{}).get("items",[]):
        selected=[item for item in wrapper.get("items",[]) if item.get("notify")]
        if selected: metrics.append({**wrapper,"items":selected})
    horizon=[p for p in payloads.get("marc_horizon",{}).get("items",[]) if p.get("confidence") in {"high","medium"} and p.get("notify")]
    sections=[]
    warnings=[{"component":k,"status":v.get("status"),"detail":v.get("detail")} for k,v in health.get("source_freshness",{}).items() if v.get("status") not in {"fresh","running"}]
    if warnings: sections.append({"section":"health","items":warnings})
    sections.append({"section":"daily_activity","items":daily})
    if packages: sections.append({"section":"high_medium_packages","items":packages})
    if standalone: sections.append({"section":"standalone_watchlist","items":standalone})
    if metrics: sections.append({"section":"supporting_metrics","items":metrics})
    if horizon: sections.append({"section":"marc_horizon","items":horizon})
    return {"schema_version":2,"generated_at":payloads.get("health",{}).get("generated_at"),"generated_at_timezone":"UTC","as_of":payloads.get("health",{}).get("as_of"),"as_of_timezone":"America/New_York","source_freshness":health.get("source_freshness",{}),"items":sections}

def _apply_lifecycle(conn, payloads: dict[str, dict], now: dt.datetime, *, commit: bool = True) -> None:
    signals = []
    refs = []
    for item in payloads.get("packages", {}).get("items", []):
        if item.get("confidence") == "low":
            item.update({"lifecycle":"diagnostic","notify":False})
            continue
        key = item.setdefault("signal_key", f"package:{item.get('package_id', item.get('label', 'unknown'))}")
        signals.append({"signal_key":key,"signal_type":"package","status":"qualified","direction":item.get("direction"),"confidence":item.get("confidence"),"payload":item})
        refs.append((item, key))
    for item in payloads.get("standalone", {}).get("items", []):
        key = item.setdefault("signal_key", f"standalone:{item.get('record_id', 'unknown')}")
        signals.append({"signal_key":key,"signal_type":"standalone","status":"qualified","confidence":"medium","payload":item})
        refs.append((item, key))
    for wrapper in payloads.get("fr_metrics", {}).get("items", []):
        if wrapper.get("metric") == "weekly_activity_spike":
            metric_items = wrapper.get("items", [])
        elif wrapper.get("metric") == "sustained_level_shift":
            metric_items = wrapper.get("items", [])
        elif wrapper.get("metric") == "rulemaking_pipeline":
            metric_items = [x for x in wrapper.get("items", []) if x.get("newly_elevated")]
        else:
            metric_items = []
        for item in metric_items:
            if not item.get("alert") and not item.get("newly_elevated"): continue
            key = item.setdefault("signal_key", f"metric:{wrapper.get('metric')}:{item.get('agency_id', item.get('agency', 'unknown'))}")
            signals.append({"signal_key":key,"signal_type":"metric","status":"qualified","confidence":"medium","payload":item})
            refs.append((item, key))
    for item in payloads.get("marc_horizon", {}).get("items", []):
        if item.get("confidence") not in {"high", "medium"}: continue
        key = item.setdefault("signal_key", f"horizon:{item.get('subject', 'unknown')}")
        signals.append({"signal_key":key,"signal_type":"horizon","status":"qualified","confidence":item.get("confidence"),"payload":item})
        refs.append((item, key))
    lifecycle = {x["signal_key"]: x for x in update_signal_state(conn, signals, now, commit=commit)}
    for item, key in refs:
        if key in lifecycle:
            item.update({"lifecycle": lifecycle[key]["lifecycle"], "notify": lifecycle[key]["notify"]})
    destinations = {"package":"packages", "standalone":"standalone", "horizon":"marc_horizon"}
    resolved_metrics=[]
    for transition in lifecycle.values():
        if transition.get("lifecycle") != "resolved": continue
        item=dict(transition.get("payload") or {})
        item.update({"signal_key":transition["signal_key"],"lifecycle":"resolved","notify":transition.get("notify",False)})
        destination=destinations.get(transition.get("signal_type"))
        if destination:
            payloads[destination].setdefault("items",[]).append(item)
        elif transition.get("signal_type") == "metric":
            resolved_metrics.append(item)
    if resolved_metrics:
        payloads["fr_metrics"].setdefault("items",[]).append({"metric":"resolved_signals","items":resolved_metrics})

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
    conn.execute("savepoint v2_output_generation")
    generation=None
    try:
        packages=persist_package_versions(conn,detect_packages(conn,as_of),now.isoformat().replace("+00:00","Z"),commit=False)
        package_members={entry["record_id"] for package in packages for entry in package.get("evidence",[])}
        standalone=[item for item in detect_standalone(conn,as_of) if item.get("record_id") not in package_members]
        activity=_daily(conn,as_of); fr_activity=compute_fr_activity(conn,as_of); level=compute_level_shifts(conn,as_of); pipe=compute_pipeline_metrics(conn,as_of); horizon=compute_marc_horizon(conn,as_of)
        horizon_payload={**horizon,**_base(as_of,now,horizon.get("items",[]),freshness)}
        payloads={"daily_activity":_base(as_of,now,[activity],freshness),"packages":_base(as_of,now,packages,freshness),"standalone":_base(as_of,now,standalone,freshness),"fr_metrics":_base(as_of,now,[fr_activity,level,pipe],freshness),"marc_horizon":horizon_payload,"health":_base(as_of,now,[{"component":k,**v} for k,v in freshness.items()],freshness)}
        _apply_lifecycle(conn,payloads,now,commit=False)
        payloads["brief"]=build_brief(payloads)
        generation=_stage_snapshot(out_dir,payloads)
        conn.execute("release v2_output_generation")
    except Exception:
        try: conn.execute("rollback to v2_output_generation"); conn.execute("release v2_output_generation")
        except Exception: pass
        if generation is not None: shutil.rmtree(generation,ignore_errors=True)
        raise
    _activate_snapshot(out_dir,generation)
    return payloads

def publish_failure_outputs(conn, as_of: str, out_dir: Path, now: dt.datetime, detail: str) -> None:
    out_dir=Path(out_dir); freshness=source_freshness(conn,now)
    payloads={name:_base(as_of,now,[],freshness) for name in OUTPUT_NAMES if name != "brief"}
    payloads["daily_activity"]=_base(as_of,now,[_daily(conn,as_of)],freshness)
    payloads["health"]=_base(as_of,now,[{"component":key,**value} for key,value in freshness.items()],freshness)
    payloads["brief"]=build_brief(payloads)
    publish_snapshot(out_dir,payloads)
