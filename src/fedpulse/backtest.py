"""Offline, pre-registered evaluation of FedPulse signals.

Predictive evaluation only accepts evidence at least 30 days before the event.
MARC/TER horizon emergence is reported separately and is not counted as a
predictive hit.  This module never ingests or mutates a production database.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import statistics
from pathlib import Path

from . import db
from .metrics_v2 import compute_fr_activity, compute_pipeline_metrics

CONFIG = Path(__file__).parent / "config" / "evaluation_events.json"
EVENTS = json.loads(CONFIG.read_text(encoding="utf-8"))["events"]
for _event in EVENTS:
    _event.setdefault("date", _event["event_date"])


def _date(event: dict) -> dt.date:
    return dt.date.fromisoformat(event.get("event_date") or event["date"])


def _check_rcr(conn, event: dict, *, as_of: dt.date | None = None) -> dict:
    event_day = as_of or _date(event)
    cutoff = event_day - dt.timedelta(days=int(event.get("lead_days_required", 30)))
    start = event_day - dt.timedelta(days=730)
    candidates = []
    day = start
    while day <= cutoff:
        result = compute_pipeline_metrics(conn, as_of=day.isoformat())
        row = next((a for a in result["items"] if a["agency"] == event.get("agency")), None)
        if row and row.get("newly_elevated"):
            candidates.append((day, row))
        day += dt.timedelta(days=7)
    if not candidates:
        return {"fired": False, "lead_days": None, "evidence_date": None, "detail": f"no RCR flag for {event.get('agency')} at least {event.get('lead_days_required',30)} days before event"}
    fire_day, row = candidates[-1]
    return {"fired": True, "lead_days": (event_day - fire_day).days, "evidence_date": fire_day.isoformat(), "detail": f"pipeline flag {fire_day}: proposal/final={row['proposal_to_final_ratio']} finals={row['final_rules']} proposals={row['proposed_rules']}"}


def _check_api(conn, event: dict) -> dict:
    event_day = _date(event); cutoff = event_day - dt.timedelta(days=int(event.get("lead_days_required", 30))); start = event_day - dt.timedelta(days=365)
    candidates = []
    day = start
    while day <= cutoff:
        result = compute_fr_activity(conn, as_of=day.isoformat())
        row = next((a for a in result["items"] if a["agency"] == event.get("agency") or a.get("agency_id") == event.get("agency")), None)
        if row and row.get("alert"):
            candidates.append((day, row))
        day += dt.timedelta(days=7)
    if not candidates:
        return {"fired": False, "lead_days": None, "evidence_date": None, "detail": f"no API flag for {event.get('agency')} at least {event.get('lead_days_required',30)} days before event"}
    fire_day, row = candidates[-1]
    return {"fired": True, "lead_days": (event_day - fire_day).days, "evidence_date": fire_day.isoformat(), "detail": f"API flag {fire_day}: z={row['z_score']} count={row['current_count']}"}


def _check_ter(conn, event: dict, *, predictive: bool = False) -> dict:
    event_day = _date(event); lead = int(event.get("lead_days_required", 30)) if predictive else 0; cutoff = event_day - dt.timedelta(days=lead)
    needle = str(event.get("subject", "")).casefold()
    row = conn.execute("select s.subject, s.first_seen_date, s.first_agency from subject_first_seen s join records r on r.id=s.first_record_id and r.source='marc' where lower(s.subject)=? order by s.first_seen_date limit 1", (needle,)).fetchone()
    if not row:
        return {"fired": False, "lead_days": None, "evidence_date": None, "detail": f"subject '{event.get('subject')}' not found"}
    first = dt.date.fromisoformat(row["first_seen_date"])
    if first > event_day:
        return {"fired": False, "lead_days": None, "evidence_date": row["first_seen_date"], "detail": "rejected: TER evidence occurs after the event date"}
    if predictive and first > cutoff:
        return {"fired": False, "lead_days": (event_day - first).days, "evidence_date": row["first_seen_date"], "detail": f"rejected: TER evidence has only {(event_day-first).days} days of lead; requires {lead}"}
    return {"fired": True, "lead_days": (event_day - first).days, "evidence_date": row["first_seen_date"], "detail": f"'{row['subject']}' first_seen {row['first_seen_date']} ({row['first_agency']})"}


def check(conn, event: dict) -> dict:
    event = dict(event); event.setdefault("event_date", event.get("date")); event.setdefault("date", event["event_date"])
    signal_class = event.get("signal_class", "predictive")
    if signal_class == "horizon": result = _check_ter(conn, event, predictive=False)
    elif event.get("index") == "rcr": result = _check_rcr(conn, event)
    elif event.get("index") == "api": result = _check_api(conn, event)
    elif event.get("index") == "ter": result = _check_ter(conn, event, predictive=True)
    else: result = {"fired": False, "lead_days": None, "evidence_date": None, "detail": f"unknown index {event.get('index')}"}
    return {"event":event["name"],"date":event["event_date"],"index":event.get("index"),"signal_class":signal_class,"lead_days_required":event.get("lead_days_required",30),**result}


def _negative_control(conn, event: dict, control: dict) -> dict:
    probe = dict(event); probe["event_date"] = control["date"]; probe["date"] = control["date"]
    if event.get("index") == "ter": result = _check_ter(conn, probe, predictive=False)
    elif event.get("index") == "rcr": result = _check_rcr(conn, probe)
    else: result = _check_api(conn, probe)
    return {"name":control.get("name"),"date":control["date"],"fired":bool(result.get("fired")),"detail":result.get("detail","")}


def evaluate_events(conn, events: list[dict] | None = None) -> dict:
    events = events or EVENTS
    results = [check(conn, event) for event in events]
    predictive = [r for r in results if r["signal_class"] == "predictive"]
    horizon = [r for r in results if r["signal_class"] == "horizon"]
    predictive_controls = []
    horizon_controls = []
    for event in events:
        controls = event.get("negative_controls") or []
        target = horizon_controls if event.get("signal_class") == "horizon" else predictive_controls
        target.extend(_negative_control(conn,event,control) for control in controls)
    tp = sum(r["fired"] for r in predictive); fn = len(predictive) - tp; fp = sum(c["fired"] for c in predictive_controls); tn = len(predictive_controls) - fp
    leads = [r["lead_days"] for r in predictive if r["fired"] and r["lead_days"] is not None]
    return {"predictive":{"events":predictive,"true_positives":tp,"false_negatives":fn,"precision":tp/(tp+fp) if tp+fp else 0.0,"recall":tp/(tp+fn) if tp+fn else 0.0,"false_positive_rate":fp/(fp+tn) if fp+tn else 0.0,"median_lead_days":statistics.median(leads) if leads else None,"negative_controls":predictive_controls},"horizon":{"events":horizon,"negative_controls":horizon_controls,"note":"Horizon emergence is descriptive and excluded from predictive precision/recall."},"negative_controls":predictive_controls}


def render_report(report: dict) -> str:
    lines = ["# FedPulse v0.2 honest evaluation", "", "Predictive signals require the pre-registered lead window; horizon signals are reported separately.", ""]
    p = report["predictive"]
    lines.append(f"Predictive precision={p['precision']:.3f}; recall={p['recall']:.3f}; FPR={p['false_positive_rate']:.3f}; median lead={p['median_lead_days']}")
    for section in ("predictive", "horizon"):
        lines.append(f"\n## {section.title()}")
        for result in report[section]["events"]:
            lines.append(f"- {'PASS' if result['fired'] else 'MISS'} {result['event']} — lead={result['lead_days']} — {result['detail']}")
    lines.append("\n## Negative controls")
    for control in report["negative_controls"]:
        lines.append(f"- {'FIRED' if control['fired'] else 'quiet'} {control['name']} ({control['date']}) — {control['detail']}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("--db", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "fedpulse.db"); parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parents[2] / "data" / "outputs" / "backtest.md")
    args = parser.parse_args(argv); conn = db.connect(args.db); report = evaluate_events(conn); text = render_report(report); args.out.parent.mkdir(parents=True, exist_ok=True); args.out.write_text(text, encoding="utf-8"); print(text, end=""); conn.close(); return 0

if __name__ == "__main__":
    raise SystemExit(main())
