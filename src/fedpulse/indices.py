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
API_MIN_WEEKS = 6       # agency must appear in >= 6 distinct weeks of the window
API_MIN_CURRENT = 3     # current-week count must be >= 3 to count as a real spike
RCR_THRESHOLD = 5.0     # flag churn ratio >= 5:1 (absolute)
RCR_Z_THRESHOLD = 2.5   # flag when RCR z-score vs own 12-month history >= 2.5σ
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
    """Agency Pulse Index: weekly counts per agency; z-score of current week vs prior 8 weeks.

    Only the last 16 weeks of records are needed (8-week baseline + current) —
    filter in SQL instead of scanning the full catalog.
    """
    as_of = as_of or dt.date.today().isoformat()
    as_of_day = dt.date.fromisoformat(as_of)
    cutoff = (as_of_day - dt.timedelta(weeks=16)).isoformat()
    rows = conn.execute(
        """SELECT agency, COALESCE(cataloged_date, publication_date, '') AS d FROM records
           WHERE agency IS NOT NULL AND agency != ''
             AND (cataloged_date >= ? OR (cataloged_date IS NULL AND publication_date >= ?))""",
        (cutoff, cutoff),
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
        if len(series) < API_MIN_WEEKS:
            continue  # not enough presence history → not a measurable pulse
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
        flagged = z >= API_Z_THRESHOLD and cur >= API_MIN_CURRENT
        agencies.append({
            "agency": agency,
            "current_week": series[-1][0] if series else None,
            "current_count": cur,
            "baseline_mean": round(mean, 2),
            "baseline_std": round(stdev, 2),
            "z_score": z_disp,
            "flagged": flagged,
            "series": [{"week": w, "count": c} for w, c in series[-12:]],
        })

    agencies.sort(key=lambda a: (a["flagged"], a["z_score"] or -1), reverse=True)
    return {"as_of": as_of, "threshold": API_Z_THRESHOLD, "agencies": agencies}


def compute_rcr(conn, as_of: str | None = None) -> dict:
    """Regulatory Churn Ratio per agency (FR docs only): (proposed+notice)/final.

    Computes the ratio over 24 overlapping 12-month windows ending at each
    month-end. Flags when the CURRENT ratio is >=2.5σ above the agency's own
    history (relative churn — works for high-volume agencies like EPA) OR the
    absolute ratio is >= 5:1 (drafting-mode alarm).
    """
    as_of = as_of or dt.date.today().isoformat()
    end = dt.date.fromisoformat(as_of)
    hist_start = end - dt.timedelta(days=730)  # 24 months for baseline windows
    rows = conn.execute(
        """SELECT agency, doc_type, publication_date FROM records
           WHERE source='fr' AND doc_type IS NOT NULL AND publication_date >= ? AND publication_date <= ?""",
        (hist_start.isoformat(), end.isoformat()),
    ).fetchall()

    # per agency: list of (month_start, proposed, notice, final)
    events: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for r in rows:
        t = r["doc_type"].lower().replace("-", "_").replace(" ", "_")
        if t in ("rule", "proposed_rule", "notice") and r["agency"]:
            events[r["agency"]].append((t, r["publication_date"]))

    month_ends = []
    d = end.replace(day=28) + dt.timedelta(days=4)
    for _ in range(24):
        d = d.replace(day=1) - dt.timedelta(days=1)
        month_ends.append(d)
    month_ends.reverse()

    out = []
    for agency, evs in events.items():
        series = []
        for me in month_ends:
            win_start = (me - dt.timedelta(days=365)).isoformat()
            me_iso = me.isoformat()
            props = sum(1 for t, d in evs if t == "proposed_rule" and win_start <= d <= me_iso)
            notices = sum(1 for t, d in evs if t == "notice" and win_start <= d <= me_iso)
            finals = sum(1 for t, d in evs if t == "rule" and win_start <= d <= me_iso)
            ratio = (props + notices) / finals if finals >= RCR_MIN_FINALS else None
            series.append({"window_end": me_iso, "proposed": props, "notices": notices, "final": finals, "ratio": ratio})

        finite = [s["ratio"] for s in series if s["ratio"] is not None]
        if not finite:
            continue
        cur = series[-1]
        cur_ratio = cur["ratio"]
        baseline = finite[:-1]
        mean = statistics.mean(baseline) if len(baseline) >= 3 else 0.0
        stdev = statistics.stdev(baseline) if len(baseline) > 3 else 0.0
        if stdev > 0 and cur_ratio is not None:
            z = (cur_ratio - mean) / stdev
        elif cur_ratio is not None and cur_ratio > mean and len(baseline) >= 3:
            z = float("inf")
        else:
            z = 0.0
        z_disp = round(min(z, 99.9), 2) if math.isfinite(z) else 99.9
        flagged = (z >= RCR_Z_THRESHOLD) or (cur_ratio is not None and cur_ratio >= RCR_THRESHOLD)
        out.append({
            "agency": agency,
            "window_start": series[-1]["window_end"][:8] + "01" if series else None,
            "window_end": series[-1]["window_end"] if series else None,
            "final_rules": cur["final"],
            "proposed_rules": cur["proposed"],
            "notices": cur["notices"],
            "other": 0,
            "churn_ratio": round(cur_ratio, 2) if cur_ratio is not None else None,
            "z_score": z_disp,
            "baseline_mean": round(mean, 2),
            "flagged": flagged,
            "series": series[-12:],
        })
    out.sort(key=lambda a: (a["flagged"], a["z_score"] or -1), reverse=True)
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
        """SELECT subjects, COALESCE(cataloged_date, publication_date, '') AS d, agency FROM records
           WHERE subjects != '[]' AND subjects IS NOT NULL
             AND (cataloged_date >= ? OR (cataloged_date IS NULL AND publication_date >= ?))""",
        (accel_start, accel_start),
    ).fetchall()
    weekly: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    agencies_by_subject: dict[str, set[str]] = defaultdict(set)
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
            if r["agency"]:
                agencies_by_subject[s].add(r["agency"])

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
        distinct = len(agencies_by_subject.get(subj, set()))
        # require >=2 distinct agencies in the window to filter batch/series artifacts
        if weekly_mean > 0 and cur4 >= 4 and distinct >= 2 and cur4 / (weekly_mean * 4) >= TER_ACCEL_MULT:
            accel.append({
                "subject": subj,
                "last_4w_count": cur4,
                "prior_weekly_mean": round(weekly_mean, 2),
                "multiple": round(cur4 / (weekly_mean * 4), 2),
                "distinct_agencies": distinct,
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
