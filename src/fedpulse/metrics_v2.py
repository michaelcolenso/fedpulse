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

def _agency_key(row: sqlite3.Row) -> str:
    return row["canonical_agency_id"] or row["agency"] or "unmapped"

def _series(conn: sqlite3.Connection, as_of: str, count: int = 17) -> tuple[list[dict], list[tuple[date,date]]]:
    weeks = complete_publication_weeks(date.fromisoformat(as_of), count)
    rows = conn.execute("select publication_date from records where source='fr' and publication_date is not null").fetchall()
    dates = [date.fromisoformat(r[0]) for r in rows]
    result = []
    for start, end in weeks:
        result.append({"week_start": start.isoformat(), "week_end": end.isoformat(), "count": sum(start <= d <= end for d in dates)})
    return result, weeks

def _agency_series(conn: sqlite3.Connection, as_of: str, count: int) -> dict[str, tuple[str, list[dict]]]:
    weeks = complete_publication_weeks(date.fromisoformat(as_of), count)
    rows = conn.execute("select canonical_agency_id, canonical_agency_name, agency, publication_date from records where source='fr' and publication_date is not null").fetchall()
    grouped: dict[str, tuple[str, list[date]]] = {}
    for row in rows:
        key = _agency_key(row)
        label = row["canonical_agency_name"] or row["agency"] or key
        if key not in grouped:
            grouped[key] = (label, [])
        grouped[key][1].append(date.fromisoformat(row["publication_date"]))
    out = {}
    for key, (label, dates) in grouped.items():
        out[key] = (label, [{"week_start": start.isoformat(), "week_end": end.isoformat(), "count": sum(start <= d <= end for d in dates)} for start, end in weeks])
    return out

def _activity_item(agency_id: str, agency: str, series: list[dict]) -> dict:
    baseline_counts = [x["count"] for x in series[:-1]]
    current = series[-1]["count"] if series else 0
    mean = statistics.fmean(baseline_counts) if baseline_counts else 0.0
    sd = statistics.pstdev(baseline_counts) if len(baseline_counts) > 1 else 0.0
    item = {"agency_id": agency_id, "agency": agency, "weeks": series, "baseline_sample_size": len(baseline_counts), "baseline_raw_weekly_counts": baseline_counts, "current_count": current, "baseline_mean": round(mean, 6), "baseline_stddev": round(sd, 6), "alert": False}
    if len(baseline_counts) < 8 or current < 3:
        item["statistical_evidence"] = "insufficient_sample"
    elif sd == 0:
        item["statistical_evidence"] = "insufficient_zero_variance"
    elif mean >= 5:
        z = (current - mean) / sd
        item["z_score"] = round(z, 6); item["statistical_evidence"] = "z_score"; item["alert"] = z >= 2.5
    else:
        p = poisson_upper_tail(current, mean)
        item["poisson_upper_tail"] = round(p, 8); item["statistical_evidence"] = "exact_poisson"; item["alert"] = p <= .01 and current >= 5 and current - mean >= 3
    return item

def compute_fr_activity(conn: sqlite3.Connection, as_of: str) -> dict:
    series, _ = _series(conn, as_of, 17)
    aggregate = _activity_item("aggregate", "all agencies", series)
    items = [_activity_item(key, label, values) for key, (label, values) in sorted(_agency_series(conn, as_of, 17).items())]
    return {**_meta(as_of), "source":"federal_register", "metric":"weekly_activity_spike", **aggregate, "items":items, "aggregate":aggregate, "alert":any(x["alert"] for x in items)}

def compute_level_shifts(conn: sqlite3.Connection, as_of: str) -> dict:
    series, _ = _series(conn, as_of, 16)
    def shift(agency_id: str, agency: str, values: list[dict]) -> dict:
        baseline, recent = values[:12], values[12:]
        baseline_total = sum(x["count"] for x in baseline); recent_total = sum(x["count"] for x in recent)
        baseline_rate = baseline_total / 12 if baseline else 0.0; recent_rate = recent_total / 4 if recent else 0.0
        alert = bool(baseline_rate > 0 and recent_rate >= baseline_rate * 1.5 and recent_total >= baseline_total + 4 and sum(x["count"] > 0 for x in recent) >= 3)
        return {"signal_type":"fr_level_shift", "agency_id":agency_id, "agency":agency, "baseline_total":baseline_total, "recent_total":recent_total, "baseline_weekly_rate":round(baseline_rate, 6), "recent_weekly_rate":round(recent_rate, 6), "recent_active_weeks":sum(x["count"] > 0 for x in recent), "alert":alert, "weeks":values}
    grouped = _agency_series(conn, as_of, 16)
    items = [shift(key, label, values) for key, (label, values) in sorted(grouped.items())]
    aggregate = shift("aggregate", "all agencies", series)
    return {**_meta(as_of), "source":"federal_register", "metric":"sustained_level_shift", "items":items, "alert":any(x["alert"] for x in items), "detail":aggregate, "aggregate":aggregate}

def percentile_rank(values, value: float) -> float:
    values = sorted(float(v) for v in values)
    if not values: return 0.0
    below = sum(v < value for v in values); equal = sum(v == value for v in values)
    return round(100 * (below + .5 * equal) / len(values), 6)

def _month_shift(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    return date(index // 12, index % 12 + 1, 1)

def _window_counts(rows, start: date, end: date) -> dict[str, int]:
    out = {"proposed_rules": 0, "final_rules": 0, "notices": 0}
    for row in rows:
        d = date.fromisoformat(row["publication_date"])
        if not start <= d <= end: continue
        typ = (row["doc_type"] or "").lower().replace("-", "_").replace(" ", "_")
        if typ in {"rule", "final_rule"}: out["final_rules"] += 1
        elif typ == "proposed_rule": out["proposed_rules"] += 1
        elif typ == "notice": out["notices"] += 1
    return out

def _ratio(counts: dict[str, int]) -> float | None:
    return counts["proposed_rules"] / counts["final_rules"] if counts["final_rules"] else None

def _eligible(counts: dict[str, int]) -> bool:
    total = sum(counts.values())
    return counts["final_rules"] >= 10 or (total >= 50 and counts["final_rules"] >= 5)

def compute_pipeline_metrics(conn: sqlite3.Connection, as_of: str) -> dict:
    """Compute separate proposal/final and notices workload ratios with sample/history gates."""
    end = date.fromisoformat(as_of); query_start = _month_shift(end.replace(day=1), -25)
    rows = conn.execute("select canonical_agency_id, agency, doc_type, publication_date from records where source='fr' and publication_date between ? and ?", (query_start.isoformat(), end.isoformat())).fetchall()
    agencies = sorted({r["canonical_agency_id"] or r["agency"] or "unmapped" for r in rows})
    current_values = []; items = []
    for agency in agencies:
        current_start = _month_shift(end.replace(day=1), -11)
        agency_rows = [r for r in rows if (r["canonical_agency_id"] or r["agency"] or "unmapped") == agency]
        current = _window_counts(agency_rows, current_start, end)
        current_ratio = _ratio(current); eligible = _eligible(current)
        histories = []
        for shift in range(1, 14):
            window_end = _month_shift(end.replace(day=1), -shift) - timedelta(days=1)
            window_start = _month_shift(window_end.replace(day=1), -11)
            c = _window_counts(agency_rows, window_start, window_end)
            if _eligible(c) and _ratio(c) is not None: histories.append(_ratio(c))
        prior_end = _month_shift(end.replace(day=1), -1) - timedelta(days=1)
        prior_start = _month_shift(prior_end.replace(day=1), -11)
        prior_ratio = _ratio(_window_counts(agency_rows, prior_start, prior_end))
        item = {"agency":agency, **current, "eligible":eligible, "proposal_to_final_ratio":current_ratio, "activity_to_final_ratio":(current["proposed_rules"] + current["notices"]) / current["final_rules"] if current["final_rules"] else None, "workload_metric":"activity_to_final_ratio", "history_sample_size":len(histories), "history_mean":statistics.fmean(histories) if histories else None, "history_standard_deviation":statistics.pstdev(histories) if len(histories)>1 else None, "prior_month_ratio":prior_ratio, "history_z_score":None, "current_percentile":None, "newly_elevated":False}
        if eligible and current_ratio is not None: current_values.append(current_ratio)
        items.append(item)
    for item in items:
        if not item["eligible"] or item["proposal_to_final_ratio"] is None: continue
        item["current_percentile"] = percentile_rank(current_values, item["proposal_to_final_ratio"])
        if item["history_sample_size"] >= 12 and item["history_standard_deviation"] and item["history_standard_deviation"] > 0:
            item["history_z_score"] = round((item["proposal_to_final_ratio"] - item["history_mean"]) / item["history_standard_deviation"], 6)
        history_path = item["history_z_score"] is not None and item["history_z_score"] >= 2.5 and item["current_percentile"] >= 80
        percentile_path = item["current_percentile"] >= 95 and item["prior_month_ratio"] is not None and item["proposal_to_final_ratio"] >= item["prior_month_ratio"] * 1.25
        item["newly_elevated"] = bool(history_path or percentile_path)
        item["alert_basis"] = "history_z_and_percentile" if history_path else ("cross_sectional_and_month_change" if percentile_path else None)
    return {**_meta(as_of), "source":"federal_register", "metric":"rulemaking_pipeline", "items":items, "primary_metric":"proposal_to_final_ratio", "context_metric":"activity_to_final_ratio", "history_window_months":12}
