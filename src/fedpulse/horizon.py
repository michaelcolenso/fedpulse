"""MARC-only Government Topic Horizon with explicit batch confidence."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import Counter
from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from .taxonomy import canonicalize_agency

def _subjects(row: Mapping[str, Any]) -> list[str]:
    value = row.get("subjects") or []
    if isinstance(value, str):
        try: value = json.loads(value)
        except json.JSONDecodeError: value = [value]
    return [str(v) for v in value if v]

def _row_agency(row: Mapping[str, Any]) -> str | None:
    return row.get("canonical_agency_id") or (canonicalize_agency("marc", row.get("agency") or "").canonical_id)

def horizon_confidence(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(r) for r in rows]
    dates = [r.get("cataloged_date") for r in rows if r.get("cataloged_date")]
    day_counts = Counter(dates); agencies = sorted({a for a in (_row_agency(r) for r in rows) if a})
    count = len(rows); distinct_dates = len(day_counts); max_concentration = max(day_counts.values(), default=0) / count if count else 0
    if count >= 10 and distinct_dates >= 3 and len(agencies) >= 3 and max_concentration <= .5: confidence = "high"
    elif max_concentration > .5: confidence = "catalog_batch_risk"
    else: confidence = "insufficient_sample"
    evidence=[]
    for r in sorted(rows, key=lambda x: (x.get("cataloged_date") or "", x.get("id") or "")):
        evidence.append({"record_id":r.get("id"),"official_url":r.get("url"),"title":r.get("title"),"subject":_subjects(r),"raw_agency":r.get("agency"),"canonical_agency_id":_row_agency(r),"cataloged_date":r.get("cataloged_date")})
    return {"confidence":confidence,"record_count":count,"distinct_cataloged_dates":distinct_dates,"distinct_canonical_agencies":len(agencies),"same_day_concentration":round(max_concentration,6),"first_seen_cataloged":min(dates) if dates else None,"first_seen_label":"First seen cataloged" if dates else "No cataloged records","evidence":evidence}

def compute_marc_horizon(conn: sqlite3.Connection, as_of: str, recent_days: int = 28, baseline_days: int = 56) -> dict[str, Any]:
    end = date.fromisoformat(as_of); recent_start = end - timedelta(days=recent_days - 1); baseline_start = end - timedelta(days=baseline_days - 1)
    rows = conn.execute("select * from records where source='marc' and cataloged_date between ? and ? order by cataloged_date,id", (baseline_start.isoformat(), end.isoformat())).fetchall()
    groups: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        row = dict(row)
        for subject in _subjects(row): groups.setdefault(subject, []).append(row)
    items=[]
    for subject, all_rows in sorted(groups.items()):
        recent = [r for r in all_rows if r.get("cataloged_date") and r["cataloged_date"] >= recent_start.isoformat()]
        if not recent: continue
        prior_count=sum(1 for r in all_rows if r.get("cataloged_date") and r["cataloged_date"] < recent_start.isoformat())
        first_row=conn.execute("select s.first_seen_date from subject_first_seen s join records r on r.id=s.first_record_id and r.source='marc' where lower(s.subject)=lower(?)",(subject,)).fetchone()
        global_first=first_row[0] if first_row else min(r["cataloged_date"] for r in all_rows if r.get("cataloged_date"))
        agencies={_row_agency(r) for r in recent if _row_agency(r)}
        is_new=global_first >= recent_start.isoformat()
        is_accelerating=prior_count > 0 and len(recent) >= max(3, prior_count * 2) and len(agencies) >= 2
        if not (is_new or is_accelerating): continue
        item = horizon_confidence(recent); item.update({"subject":subject,"horizon_state":"new" if is_new else "accelerating","last_four_week_catalog_count":len(recent),"prior_baseline_count":prior_count,"first_seen_cataloged":global_first,"first_seen_label":"First seen cataloged","selection_reason":"first seen in recent catalog window" if is_new else "recent catalog count at least doubled baseline across two agencies","comparison_basis":"last 4 catalog weeks versus prior 4 catalog weeks","source_cadence":"monthly_gpo_maintenance","confidence_reasons":[f"{len(recent)} recent records",f"{len(agencies)} canonical agencies",f"first cataloged {global_first}"],"source":"marc","date_basis":"cataloged_date"})
        items.append(item)
    return {"schema_version":2,"as_of":as_of,"as_of_timezone":"America/New_York","generated_at":dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z"),"generated_at_timezone":"UTC","source":"marc","catalog_date_field":"cataloged_date","items":items}
