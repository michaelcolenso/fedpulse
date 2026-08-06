"""Backtest: did the indices fire before known regulatory events?

This is the sales deck. For each event in EVENTS, check whether the relevant
index crossed its threshold in the lookback window before the event date.

Run: PYTHONPATH=src uv run python -m fedpulse.backtest   (needs populated fedpulse.db)
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import db, indices

# Known regulatory events + which index should have fired first.
# agency must match the agency string in the DB (FR child agency names).
EVENTS = [
    {
        "name": "SEC climate disclosure — final rule",
        "date": "2024-03-06",
        "index": "rcr",
        "agency": "Securities and Exchange Commission",
        "expect": "SEC RCR elevated in 2022-2023 (proposed rule era)",
    },
    {
        "name": "FTC non-compete — final rule",
        "date": "2024-04-23",
        "index": "rcr",
        "agency": "Federal Trade Commission",
        "expect": "FTC churn spike when proposed Jan 2023",
    },
    {
        "name": "EPA PFAS drinking water standards — final",
        "date": "2024-04-10",
        "index": "rcr",
        "agency": "Environmental Protection Agency",
        "expect": "EPA proposal Mar 2023 → elevated churn",
    },
    {
        "name": "EPA PFAS Action Plan — policy push",
        "date": "2019-02-14",
        "index": "ter",
        "subject": "Perfluorinated chemicals--Health aspects.",
        "expect": "TER caught the PFAS health heading emerging Feb 2019 — 5 years before the 2024 final rule",
    },
    {
        "name": "CFPB late fees — final rule",
        "date": "2024-03-05",
        "index": "rcr",
        "agency": "Consumer Financial Protection Bureau",
        "expect": "CFPB proposal Jan 2023 → elevated churn",
    },
    {
        "name": "SEC money market fund reforms — proposal wave",
        "date": "2022-02-08",
        "index": "api",
        "agency": "Securities and Exchange Commission",
        "expect": "SEC volume z-score elevated in the 90 days before the proposal",
    },
    {
        "name": "FDA COVID booster era — output mode",
        "date": "2021-09-01",
        "index": "api",
        "agency": "Food and Drug Administration",
        "expect": "FDA volume spike in the 90 days before Sept 2021",
    },
    {
        "name": "FCC net neutrality reinstatement — final",
        "date": "2024-04-25",
        "index": "rcr",
        "agency": "Federal Communications Commission",
        "expect": "FCC proposal Oct 2023 → elevated churn",
    },
    {
        "name": "Blockchain policy wave — congressional hearings + SEC guidance",
        "date": "2018-06-01",
        "index": "ter",
        "subject": "Blockchains (Databases)",
        "expect": "TER caught the blockchain subject heading emerging June 2018",
    },
]


def _check_rcr(conn, event: dict) -> dict:
    rcr = indices.compute_rcr(conn, as_of=event["date"])
    for a in rcr["agencies"]:
        if a["agency"] == event["agency"]:
            return {
                "fired": bool(a["flagged"]),
                "detail": (f"ratio={a['churn_ratio']} finals={a['final_rules']} "
                           f"props={a['proposed_rules']} notices={a['notices']}"),
            }
    return {"fired": False, "detail": f"agency '{event['agency']}' not in DB at that date"}


def _check_api(conn, event: dict) -> dict:
    ev_date = dt.date.fromisoformat(event["date"])
    best = None
    for offset in range(0, 14):  # scan 13 weeks back from event date
        d = (ev_date - dt.timedelta(weeks=offset)).isoformat()
        api = indices.compute_api(conn, as_of=d)
        for a in api["agencies"]:
            if a["agency"] == event["agency"]:
                if best is None or (a["flagged"] and not best[0]):
                    best = (a["flagged"], a["z_score"], a["current_count"], d)
                break
    if best is None:
        return {"fired": False, "detail": f"agency '{event['agency']}' not in DB at that date"}
    fired, z, cnt, d = best
    return {"fired": fired, "detail": f"best week {d}: z={z} count={cnt}"}


def _check_ter(conn, event: dict) -> dict:
    ev_date = dt.date.fromisoformat(event["date"])
    # emergence window: subject first appeared within ±30 days of the event
    start = (ev_date - dt.timedelta(days=30)).isoformat()
    end = (ev_date + dt.timedelta(days=30)).isoformat()
    needle = event["subject"].lower()
    cur = conn.execute(
        """SELECT subject, first_seen_date, first_agency FROM subject_first_seen
           WHERE lower(subject) = ? AND first_seen_date >= ? AND first_seen_date <= ?""",
        (needle, start, end),
    ).fetchone()
    if cur:
        return {"fired": True, "detail": f"'{cur['subject']}' first_seen {cur['first_seen_date']} ({cur['first_agency']})"}
    # fall back: exact subject anywhere in TER output at event date
    ter = indices.compute_ter(conn, as_of=event["date"])
    for s in ter["new_subjects"]:
        if s["subject"].lower() == needle:
            return {"fired": True, "detail": f"in TER new_subjects: first {s['first_seen']}"}
    return {"fired": False, "detail": f"subject '{event['subject']}' not found emerging near event"}


def check(conn, event: dict) -> dict:
    result = {"event": event["name"], "date": event["date"], "index": event["index"], "fired": False, "detail": ""}
    idx = event["index"]
    if idx == "rcr":
        r = _check_rcr(conn, event)
    elif idx == "api":
        r = _check_api(conn, event)
    elif idx == "ter":
        r = _check_ter(conn, event)
    else:
        r = {"fired": False, "detail": f"unknown index {idx}"}
    result.update(r)
    return result


def main(argv: list[str] | None = None) -> int:
    conn = db.connect(Path(__file__).resolve().parents[2] / "data" / "fedpulse.db")
    out = Path(__file__).resolve().parents[2] / "data" / "outputs" / "backtest.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    lines = ["# FedPulse Backtest — did the indices fire early?\n", f"Run: {dt.date.today().isoformat()}\n"]
    passed = 0
    for ev in EVENTS:
        r = check(conn, ev)
        mark = "PASS" if r["fired"] else "MISS"
        if r["fired"]:
            passed += 1
        lines.append(f"## {mark}: {r['event']} ({r['date']})\n- index: {r['index']}\n- {r['detail']}\n- expected: {ev['expect']}\n")
    lines.append(f"\n**{passed}/{len(EVENTS)} fired**\n")
    text = "\n".join(lines)
    out.write_text(text)
    print(text)
    conn.close()
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
