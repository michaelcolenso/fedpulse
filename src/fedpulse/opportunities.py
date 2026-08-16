"""Deterministic relevance ranking for FedPulse government-action events."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

CONFIG_PATH = Path(__file__).with_name("config") / "watch_profiles.json"


def load_profile(name: str = "default", path: Path = CONFIG_PATH) -> dict[str, Any]:
    profiles = json.loads(Path(path).read_text())
    if name not in profiles:
        raise KeyError(f"unknown watch profile: {name}")
    return profiles[name]


def _date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _payload(row) -> dict:
    value = row["payload_json"] if "payload_json" in row.keys() else None
    try:
        return json.loads(value or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _haystack(row, payload: dict) -> str:
    return " ".join(str(x or "") for x in (
        row["title"], row["agency"], row["stage"], json.dumps(payload, ensure_ascii=False)
    )).lower()


def _identifiers(conn, event_id: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for row in conn.execute("SELECT namespace,value FROM government_identifiers WHERE event_id=?", (event_id,)):
        out.setdefault(row["namespace"], []).append(row["value"])
    return out


def _deadline(payload: dict) -> dt.date | None:
    row = payload.get("row") if isinstance(payload.get("row"), dict) else payload
    for key in ("ResponseDeadLine", "response_deadline", "CloseDate", "closedate", "close_date"):
        value = row.get(key) if isinstance(row, dict) else None
        parsed = _date(value)
        if parsed:
            return parsed
    return None


def score_event(row, identifiers: dict[str, list[str]], profile: dict, as_of: dt.date) -> dict[str, Any] | None:
    payload = _payload(row)
    haystack = _haystack(row, payload)
    event_date = _date(row["event_date"])
    lookback = int(profile.get("lookback_days", 7))
    if not event_date or (as_of - event_date).days < 0 or (as_of - event_date).days > lookback:
        return None

    score = max(0, 28 - (as_of - event_date).days * 4)
    reasons: list[str] = []

    keyword_hits = [x for x in profile.get("keywords", []) if x.lower() in haystack]
    if keyword_hits:
        score += min(26, 8 + len(set(keyword_hits)) * 3)
        reasons.append("topic: " + ", ".join(sorted(set(keyword_hits))[:4]))

    geo_hits = [x for x in profile.get("geographies", []) if x.lower() in haystack]
    if geo_hits:
        score += 24
        reasons.append("geography: " + ", ".join(sorted(set(geo_hits))[:3]))

    naics = set(identifiers.get("naics", []))
    wanted_naics = set(str(x) for x in profile.get("naics", []))
    naics_hits = sorted(naics & wanted_naics)
    if naics_hits:
        score += 26
        reasons.append("NAICS: " + ", ".join(naics_hits[:3]))

    agency = str(row["agency"] or "")
    agency_hits = [x for x in profile.get("agencies", []) if x.lower() in agency.lower()]
    if agency_hits:
        score += 9
        reasons.append("agency: " + agency_hits[0])

    amount = row["amount"]
    if amount is not None:
        amount = float(amount)
        if abs(amount) >= float(profile.get("high_value_amount", 500000)):
            score += 10
            reasons.append(f"value: ${abs(amount):,.0f}")
        elif abs(amount) >= float(profile.get("minimum_amount", 25000)):
            score += 5
            reasons.append(f"value: ${abs(amount):,.0f}")

    deadline = _deadline(payload)
    days_to_close = (deadline - as_of).days if deadline else None
    if days_to_close is not None and 0 <= days_to_close <= int(profile.get("closing_soon_days", 10)):
        score += 12
        reasons.append(f"closes in {days_to_close} days")

    kind = str(row["kind"] or "")
    if kind in {"contract_opportunity", "funding_opportunity"}:
        score += 8
    elif kind == "federal_award_action" and amount and amount != 0:
        score += 4

    # Avoid filling the product with merely fresh but irrelevant bulk records.
    if not (keyword_hits or geo_hits or naics_hits or agency_hits):
        return None

    return {
        "event_id": row["event_id"],
        "source": row["source"],
        "kind": kind,
        "stage": row["stage"],
        "title": row["title"],
        "agency": row["agency"],
        "event_date": row["event_date"],
        "amount": amount,
        "currency": row["currency"],
        "official_url": row["official_url"],
        "score": round(score, 1),
        "reasons": reasons,
        "days_to_close": days_to_close,
        "identifiers": identifiers,
    }


def rank_opportunities(conn, as_of: str, profile_name: str = "default", limit: int = 30) -> list[dict[str, Any]]:
    profile = load_profile(profile_name)
    today = dt.date.fromisoformat(as_of)
    rows = conn.execute(
        """SELECT * FROM government_events
           WHERE kind IN ('contract_opportunity','funding_opportunity','federal_award_action','stakeholder_meeting','legislative_update')
           ORDER BY COALESCE(event_date,'') DESC,last_seen DESC"""
    ).fetchall()
    ranked = []
    for row in rows:
        item = score_event(row, _identifiers(conn, row["event_id"]), profile, today)
        if item:
            ranked.append(item)
    ranked.sort(key=lambda x: (-x["score"], x.get("days_to_close") if x.get("days_to_close") is not None else 9999, x["event_id"]))
    return ranked[:limit]
