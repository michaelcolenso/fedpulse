"""Honest Federal Register-only calendar metrics for v0.2."""
from __future__ import annotations

import datetime as dt
import math
import sqlite3
import statistics
from datetime import date, timedelta
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")

def complete_publication_weeks(as_of: date, count: int) -> list[tuple[date, date]]:
    """Return complete Mon-Fri weeks ending before the week containing as_of."""
    monday = as_of - timedelta(days=as_of.weekday())
    return [(monday - timedelta(days=7 * i + 7), monday - timedelta(days=7 * i + 3)) for i in range(count - 1, -1, -1)]

def poisson_upper_tail(k: int, mean: float) -> float:
    if k <= 0: return 1.0
    if mean <= 0: return 0.0
    probability = math.exp(-mean)
    cumulative = probability
    for i in range(1, k):
        probability *= mean / i
        cumulative += probability
    return max(0.0, min(1.0, 1.0 - cumulative))

def _meta(as_of: str) -> dict:
    return {"as_of": as_of, "as_of_timezone": "America/New_York", "generated_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"), "generated_at_timezone": "UTC"}

def _series(conn: sqlite3.Connection, as_of: str, count: int = 17) -> tuple[list[dict], list[tuple[date,date]]]:
    weeks = complete_publication_weeks(date.fromisoformat(as_of), count)
    rows = conn.execute("select publication_date from records where source='fr' and publication_date is not null").fetchall()
    dates = [date.fromisoformat(r[0]) for r in rows]
    result = []
    for start, end in weeks:
        result.append({"week_start": start.isoformat(), "week_end": end.isoformat(), "count": sum(start <= d <= end for d in dates)})
    return result, weeks

def compute_fr_activity(conn: sqlite3.Connection, as_of: str) -> dict:
    series, _ = _series(conn, as_of, 17)
    baseline_counts = [x["count"] for x in series[:-1]]; current = series[-1]["count"]
    mean = statistics.fmean(baseline_counts) if baseline_counts else 0.0
    sd = statistics.pstdev(baseline_counts) if len(baseline_counts) > 1 else 0.0
    result = {**_meta(as_of), "source":"federal_register", "metric":"weekly_activity_spike", "weeks":series, "baseline_sample_size":len(baseline_counts), "baseline_raw_weekly_counts":baseline_counts, "current_count":current, "baseline_mean":round(mean, 6), "baseline_stddev":round(sd, 6), "alert":False}
    if len(baseline_counts) < 8 or current < 3:
        result["statistical_evidence"] = "insufficient_sample"; return result
    if sd == 0:
        result["statistical_evidence"] = "insufficient_zero_variance"
        return result
    if mean >= 5:
        z = (current - mean) / sd
        result["z_score"] = round(z, 6); result["statistical_evidence"] = "z_score"; result["alert"] = z >= 2.5
    else:
        p = poisson_upper_tail(current, mean)
        result["poisson_upper_tail"] = round(p, 8); result["statistical_evidence"] = "exact_poisson"; result["alert"] = p <= .01 and current >= 5 and current - mean >= 3
    return result

def compute_level_shifts(conn: sqlite3.Connection, as_of: str) -> dict:
    series, _ = _series(conn, as_of, 16)
    baseline = series[:12]; recent = series[12:]
    baseline_total = sum(x["count"] for x in baseline); recent_total = sum(x["count"] for x in recent)
    baseline_rate = baseline_total / 12 if baseline else 0.0; recent_rate = recent_total / 4 if recent else 0.0
    alert = bool(baseline_rate > 0 and recent_rate >= baseline_rate * 1.5 and recent_total >= baseline_total + 4 and sum(x["count"] > 0 for x in recent) >= 3)
    item = {"signal_type":"fr_level_shift", "baseline_total":baseline_total, "recent_total":recent_total, "baseline_weekly_rate":round(baseline_rate, 6), "recent_weekly_rate":round(recent_rate, 6), "recent_active_weeks":sum(x["count"] > 0 for x in recent), "alert":alert, "weeks":series}
    return {**_meta(as_of), "source":"federal_register", "metric":"sustained_level_shift", "items":[item] if alert else [], "alert":alert, "detail":item}

def percentile_rank(values, value: float) -> float:
    values = sorted(float(v) for v in values)
    if not values: return 0.0
    below = sum(v < value for v in values); equal = sum(v == value for v in values)
    return round(100 * (below + .5 * equal) / len(values), 6)

def compute_pipeline_metrics(conn: sqlite3.Connection, as_of: str) -> dict:
    """Compute FR-only rolling proposal/final and notices workload ratios."""
    end = date.fromisoformat(as_of); start = end - timedelta(days=365)
    rows = conn.execute("select canonical_agency_id, agency, doc_type, publication_date from records where source='fr' and publication_date between ? and ?", (start.isoformat(), end.isoformat())).fetchall()
    counts: dict[str, dict[str,int]] = {}
    for row in rows:
        key = row["canonical_agency_id"] or row["agency"] or "unmapped"
        counts.setdefault(key, {"proposed_rules":0,"final_rules":0,"notices":0})
        typ = (row["doc_type"] or "").lower().replace("-", "_").replace(" ", "_")
        if typ in {"rule","final_rule"}: counts[key]["final_rules"] += 1
        elif typ == "proposed_rule": counts[key]["proposed_rules"] += 1
        elif typ == "notice": counts[key]["notices"] += 1
    eligible = []; items=[]
    for agency, c in sorted(counts.items()):
        total = sum(c.values()); eligible_flag = c["final_rules"] >= 10 or (total >= 50 and c["final_rules"] >= 5)
        primary = c["proposed_rules"] / c["final_rules"] if c["final_rules"] else None
        workload = (c["proposed_rules"] + c["notices"]) / c["final_rules"] if c["final_rules"] else None
        if eligible_flag and primary is not None: eligible.append(primary)
        items.append({"agency":agency, **c, "eligible":eligible_flag, "proposal_to_final_ratio":primary, "activity_to_final_ratio":workload, "workload_metric":"activity_to_final_ratio"})
    for item in items:
        if item["proposal_to_final_ratio"] is not None and item["eligible"]:
            item["current_percentile"] = percentile_rank(eligible, item["proposal_to_final_ratio"])
            item["newly_elevated"] = item["current_percentile"] >= 95
        else: item["current_percentile"] = None; item["newly_elevated"] = False
    return {**_meta(as_of), "source":"federal_register", "metric":"rulemaking_pipeline", "items":items, "primary_metric":"proposal_to_final_ratio", "context_metric":"activity_to_final_ratio"}
