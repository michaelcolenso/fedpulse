"""The three proprietary indices — pure counts, no NLP.

  API  Agency Pulse Index     4-week rolling z-score of publication volume per agency.
  RCR  Regulatory Churn Ratio (Proposed + Notices) / Final over rolling 12-month windows.
  TER  Topic Emergence Radar  new / accelerating LC subject headings.

Reads SQLite (records + subject_first_seen), writes JSON snapshots to data/outputs/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from . import db

OUT_DIR = Path(__file__).resolve().parents[2] / "data" / "outputs"

API_Z_THRESHOLD = 2.5   # flag agencies at >= 2.5σ above baseline
RCR_THRESHOLD = 5.0     # flag churn ratio >= 5:1
RCR_MIN_FINALS = 3      # ignore ratios with tiny final counts
TER_NEW_WINDOW_DAYS = 30
TER_ACCEL_MULT = 2.0


def _week_start(d: str | None) -> str:
    if not d:
        return ""
    try:
        day = dt.date.fromisoformat(d)
    except ValueError:
        return ""
    return (day - dt.timedelta(days=day.weekday())).isoformat()


def _month_start(d: str | None) -> str:
    if not d:
        return ""
    return d[:7] + "-01"


def compute_api(conn, as_of: str | None = None) -> dict:
    """Agency Pulse Index: weekly counts per agency; z-score of current week vs prior 8 weeks."""
    as_of = as_of or dt.date.today().isoformat()
    as_of_day = dt.date.fromisoformat(as_of)
    rows = conn.execute(
        "SELECT agency, COALESCE(cataloged_date, publication_date, '') AS d FROM records WHERE agency IS NOT NULL AND agency != ''"
    ).fetchall()
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        ws = _week_start(r["d"])
        if ws:
            counts[r["agency"]][ws] += 1

    agencies = []
    for agency, weeks in counts.items():
        series = sorted(weeks.items())
        # keep last 16 weeks
        series = series[-16:]
        if not series:
            continue
        vals = [c for _, c in series]
        cur = vals[-1] if vals else 0
        baseline = vals[:-1] if len(vals) > 1 else [0]
        mean = statistics.mean(baseline) if baseline else 0.0
        stdev = statistics.stdev(baseline) if len(baseline) > 1 else 0.0
        if stdev > 0:
            z = (cur - mean) / stdev
        elif cur > mean:
            z = float("inf")  # uniform baseline, current above it → extreme spike
        else:
            z = 0.0
        z_disp = round(min(z, 999.9), 2) if math.isfinite(z) else 999.9
        agencies.append({
            "agency": agency,
            "current_week": series[-1][0] if series else None,
            "current_count": cur,
            "baseline_mean": round(mean, 2),
            "baseline_std": round(stdev, 2),
            "z_score": z_disp,
            "flagged": z >= API_Z_THRESHOLD,
            "series": [{"week": w, "count": c} for w, c in series[-12:]],
        })

    agencies.sort(key=lambda a: (a["flagged"], a["z_score"] or -1), reverse=True)
    return {"as_of": as_of, "threshold": API_Z_THRESHOLD, "agencies": agencies}


def compute_rcr(conn, as_of: str | None = None) -> dict:
    """Regulatory Churn Ratio per agency (FR docs only): (proposed+notice)/final, 12-month rolling."""
    as_of = as_of or dt.date.today().isoformat()
    end = dt.date.fromisoformat(as_of)
    start = end - dt.timedelta(days=365)
    rows = conn.execute(
        """SELECT agency, doc_type, publication_date FROM records
           WHERE source='fr' AND doc_type IS NOT NULL AND publication_date >= ? AND publication_date <= ?""",
        (start.isoformat(), end.isoformat()),
    ).fetchall()
    agg: dict[str, dict[str, int]] = defaultdict(lambda: {"rule": 0, "proposed_rule": 0, "notice": 0, "other": 0})
    for r in rows:
        t = r["doc_type"].lower()
        key = "rule" if t == "rule" else "proposed_rule" if t == "proposed rule" else "notice" if t == "notice" else "other"
        agg[r["agency"]][key] += 1

    out = []
    for agency, c in agg.items():
        numerator = c["proposed_rule"] + c["notice"]
        denominator = c["rule"]
        ratio = numerator / denominator if denominator >= RCR_MIN_FINALS else None
        out.append({
            "agency": agency,
            "window_start": start.isoformat(),
            "window_end": end.isoformat(),
            "final_rules": c["rule"],
            "proposed_rules": c["proposed_rule"],
            "notices": c["notice"],
            "other": c["other"],
            "churn_ratio": round(ratio, 2) if ratio is not None else None,
            "flagged": ratio is not None and ratio >= RCR_THRESHOLD,
        })
    out.sort(key=lambda a: (a["flagged"], a["churn_ratio"] or -1), reverse=True)
    return {"as_of": as_of, "window_days": 365, "threshold": RCR_THRESHOLD, "agencies": out}


def compute_ter(conn, as_of: str | None = None) -> dict:
    """Topic Emergence Radar: subjects first seen recently + subjects accelerating."""
    as_of = as_of or dt.date.today().isoformat()
    end = dt.date.fromisoformat(as_of)
    new_cutoff = (end - dt.timedelta(days=TER_NEW_WINDOW_DAYS)).isoformat()
    accel_start = (end - dt.timedelta(days=84)).isoformat()

    # NEW: first_seen within window
    new_rows = conn.execute(
        """SELECT subject, first_seen_date, first_record_id, first_agency
           FROM subject_first_seen WHERE first_seen_date >= ? ORDER BY first_seen_date DESC""",
        (new_cutoff,),
    ).fetchall()
    new_subjects = [
        {
            "subject": r["subject"],
            "first_seen": r["first_seen_date"],
            "agency": r["first_agency"],
            "record_id": r["first_record_id"],
        }
        for r in new_rows
    ]

    # ACCELERATING: subject counts in last 4 weeks vs prior 8-week weekly mean (records table)
    rows = conn.execute(
        """SELECT subjects, COALESCE(cataloged_date, publication_date, '') AS d FROM records
           WHERE subjects != '[]' AND subjects IS NOT NULL AND COALESCE(cataloged_date, publication_date, '') >= ?""",
        (accel_start,),
    ).fetchall()
    weekly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r in rows:
        ws = _week_start(r["d"])
        if not ws:
            continue
        try:
            subs = json.loads(r["subjects"])
        except (json.JSONDecodeError, TypeError):
            continue
        for s in subs:
            weekly[s][ws] += 1

    recent_weeks = sorted({w for w in weekly.values() for w in weekly.keys()})
    accel = []
    for subj, weeks in weekly.items():
        series = sorted(weeks.items())
        if len(series) < 2:
            continue
        cur4 = sum(c for w, c in series[-4:])
        baseline = series[:-4]
        if not baseline:
            continue
        weekly_mean = sum(c for _, c in baseline) / len(baseline)
        if weekly_mean > 0 and cur4 >= 4 and cur4 / (weekly_mean * 4) >= TER_ACCEL_MULT:
            accel.append({
                "subject": subj,
                "last_4w_count": cur4,
                "prior_weekly_mean": round(weekly_mean, 2),
                "multiple": round(cur4 / (weekly_mean * 4), 2),
            })
    accel.sort(key=lambda a: a["multiple"], reverse=True)

    return {
        "as_of": as_of,
        "new_subjects": new_subjects,
        "accelerating_subjects": accel,
    }


def write_all(conn, out_dir: Path = OUT_DIR, as_of: str | None = None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    api = compute_api(conn, as_of=as_of)
    rcr = compute_rcr(conn, as_of=as_of)
    ter = compute_ter(conn, as_of=as_of)
    (out_dir / "api.json").write_text(json.dumps(api, indent=1))
    (out_dir / "rcr.json").write_text(json.dumps(rcr, indent=1))
    (out_dir / "ter.json").write_text(json.dumps(ter, indent=1))

    n_api = sum(1 for a in api["agencies"] if a["flagged"])
    n_rcr = sum(1 for a in rcr["agencies"] if a["flagged"])
    summary = {
        "as_of": api["as_of"],
        "api_flagged": n_api,
        "rcr_flagged": n_rcr,
        "ter_new": len(ter["new_subjects"]),
        "ter_accelerating": len(ter["accelerating_subjects"]),
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=1))
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fedpulse-indices")
    ap.add_argument("--as-of", type=str, default=None)
    args = ap.parse_args(argv)
    conn = db.connect(Path(__file__).resolve().parents[2] / "data" / "fedpulse.db")
    summary = write_all(conn, as_of=args.as_of)
    print(json.dumps(summary, indent=2))
    conn.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
