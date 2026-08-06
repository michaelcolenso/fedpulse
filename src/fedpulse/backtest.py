"""Backtest: did the indices fire before known regulatory events?

This is the sales deck. For each event in EVENTS, check whether the relevant
index crossed its threshold within a lookback window before the event date.

Run: python -m fedpulse.backtest   (needs a populated fedpulse.db)
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import db, indices

# Known regulatory events + which index should have fired first.
# agency must match the FR agency name / MARC 110a string in the DB.
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
        "expect": "EPA proposed rule Mar 2023 → elevated churn",
    },
    {
        "name": "CFPB late fees — final rule",
        "date": "2024-03-05",
        "index": "rcr",
        "agency": "Consumer Financial Protection Bureau",
        "expect": "CFPB proposal Jan 2023 → elevated churn",
    },
    {
        "name": "DOE Direct Air Capture hubs — funding announcement",
        "date": "2023-02-15",
        "index": "ter",
        "subject": "direct air capture",
        "expect": "TER flagged 'Direct air capture' subject emergence in 2022",
    },
    {
        "name": "SEC money market fund reforms — proposal wave",
        "date": "2022-02-08",
        "index": "api",
        "agency": "Securities and Exchange Commission",
        "expect": "SEC volume z-score elevated late 2021",
    },
    {
        "name": "FDA COVID vaccine booster era — output mode",
        "date": "2021-09-01",
        "index": "api",
        "agency": "Food and Drug Administration",
        "expect": "FDA volume spike 2021",
    },
    {
        "name": "FCC net neutrality reinstatement — final",
        "date": "2024-04-25",
        "index": "rcr",
        "agency": "Federal Communications Commission",
        "expect": "FCC proposal Oct 2023 → elevated churn",
    },
]


def check(conn, event: dict, as_of: str | None = None) -> dict:
    idx = event["index"]
    ev_date = dt.date.fromisoformat(event["date"])
    result = {"event": event["name"], "date": event["date"], "index": idx, "fired": False, "detail": ""}

    if idx == "api":
        api = indices.compute_api(conn, as_of=event["date"])
        for a in api["agencies"]:
            if a["agency"] == event["agency"]:
                result["detail"] = f"z={a['z_score']} count={a['current_count']} flagged={a['flagged']}"
                result["fired"] = bool(a["flagged"])
                break
        else:
            result["detail"] = f"agency '{event['agency']}' not in DB yet (backfill needed?)"
    elif idx == "rcr":
        rcr = indices.compute_rcr(conn, as_of=event["date"])
        for a in rcr["agencies"]:
            if a["agency"] == event["agency"]:
                result["detail"] = (
                    f"ratio={a['churn_ratio']} finals={a['final_rules']} "
                    f"props={a['proposed_rules']} notices={a['notices']}"
                )
                result["fired"] = bool(a["flagged"])
                break
        else:
            result["detail"] = f"agency '{event['agency']}' not in DB yet (backfill needed?)"
    elif idx == "ter":
        ter = indices.compute_ter(conn, as_of=event["date"])
        needle = event["subject"]
        for s in ter["new_subjects"]:
            if needle in s["subject"].lower():
                result["detail"] = f"'{s['subject']}' first_seen {s['first_seen']}"
                result["fired"] = True
                break
        if not result["fired"]:
            for s in ter["accelerating_subjects"]:
                if needle in s["subject"].lower():
                    result["detail"] = f"'{s['subject']}' accelerating x{s['multiple']}"
                    result["fired"] = True
                    break
        if not result["fired"]:
            result["detail"] = f"subject '{needle}' not found in TER"
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
