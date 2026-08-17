#!/usr/bin/env python3
"""Use production Vectorize as candidate discovery, then re-apply hard FedPulse facts.

Semantic similarity may broaden discovery. It never establishes geography, status,
deadlines, identifiers, or other government facts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from fedpulse.canonical_text import canonical_profile_text
from fedpulse.opportunities import (
    _all_identifiers,
    _date,
    _deadline,
    _geo_haystack,
    _payload,
    _term_match,
    lane_for,
    load_profiles,
    score_event,
)

MODEL = "@cf/qwen/qwen3-embedding-0.6b"
INDEX = "fedpulse-opportunities-v1"
ALLOWED_KINDS = {"contract_opportunity", "funding_opportunity"}


def _post_json(url: str, token: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "FedPulse/vectorize-discovery",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Cloudflare HTTP {exc.code}: {body[:1000]}") from exc


def _embed(account_id: str, token: str, text: str) -> list[float]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{MODEL}"
    body = _post_json(url, token, {"text": [text]})
    vector = ((body.get("result") or {}).get("data") or [None])[0]
    if not isinstance(vector, list):
        raise RuntimeError(f"Workers AI embedding response missing vector: {body}")
    return vector


def _query(account_id: str, token: str, vector: list[float], top_k: int) -> list[dict[str, Any]]:
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/vectorize/v2/indexes/{INDEX}/query"
    body = _post_json(
        url,
        token,
        {"vector": vector, "topK": top_k, "returnMetadata": "all"},
    )
    result = body.get("result") or {}
    return list(result.get("matches") or [])


def _hard_gate(row: sqlite3.Row, profile: dict[str, Any], as_of: dt.date) -> tuple[bool, list[str], int | None]:
    """Reject semantic matches that contradict structured facts."""
    kind = str(row["kind"] or "")
    if kind not in ALLOWED_KINDS:
        return False, ["unsupported event type"], None
    event_date = _date(row["event_date"])
    lookback = int(profile.get("lookback_days", 7))
    if not event_date or not (0 <= (as_of - event_date).days <= lookback):
        return False, ["outside freshness window"], None
    payload = _payload(row)
    deadline = _deadline(payload)
    days_to_close = (deadline - as_of).days if deadline else None
    if days_to_close is not None and days_to_close < 0:
        return False, ["deadline passed"], days_to_close
    geo_hits = [
        term for term in profile.get("geographies", [])
        if _term_match(term, _geo_haystack(row, payload))
    ]
    if profile.get("require_geography") and not geo_hits:
        return False, ["required geography not proven"], days_to_close
    reasons = []
    if geo_hits:
        reasons.append("verified geography: " + ", ".join(sorted(set(geo_hits))[:3]))
    return True, reasons, days_to_close


def _semantic_item(
    row: sqlite3.Row,
    identifiers: dict[str, list[str]],
    profile: dict[str, Any],
    as_of: dt.date,
    similarity: float,
) -> dict[str, Any] | None:
    allowed, hard_reasons, days_to_close = _hard_gate(row, profile, as_of)
    if not allowed:
        return None
    deterministic = score_event(row, identifiers, profile, as_of)
    if deterministic is not None:
        item = dict(deterministic)
        item["discovery_method"] = "deterministic+vectorize"
    else:
        age = max(0, (as_of - _date(row["event_date"])).days)
        freshness = max(0, 28 - age * 4)
        semantic_component = round(similarity * 30, 2)
        urgency = 12 if days_to_close is not None and 0 <= days_to_close <= int(profile.get("closing_soon_days", 10)) else 0
        item = {
            "event_id": row["event_id"],
            "source": row["source"],
            "kind": row["kind"],
            "lane": lane_for(row["kind"], days_to_close),
            "stage": row["stage"],
            "title": row["title"],
            "agency": row["agency"],
            "event_date": row["event_date"],
            "amount": row["amount"],
            "currency": row["currency"],
            "official_url": row["official_url"],
            "score": round(freshness + semantic_component + urgency + 8, 2),
            "score_components": {
                "freshness": freshness,
                "semantic_discovery": semantic_component,
                "urgency": urgency,
                "actionability": 8,
            },
            "edge": "semantic",
            "reasons": ["semantic profile match", *hard_reasons],
            "days_to_close": days_to_close,
            "identifiers": identifiers,
            "discovery_method": "vectorize",
        }
    item["semantic_retrieval_score"] = round(similarity, 5)
    item["semantic_discovery"] = True
    item["reasons"] = list(dict.fromkeys([*(item.get("reasons") or []), *hard_reasons]))
    return item


def discover(conn: sqlite3.Connection, as_of: str, *, top_k: int, min_similarity: float) -> dict[str, Any]:
    account_id = os.environ["CLOUDFLARE_ACCOUNT_ID"]
    token = os.environ["CLOUDFLARE_API_TOKEN"]
    profiles = load_profiles()
    today = dt.date.fromisoformat(as_of)
    ids_by_event = _all_identifiers(conn)
    rows = {row["event_id"]: row for row in conn.execute("SELECT * FROM government_events")}
    out: dict[str, Any] = {}
    for name, profile in profiles.items():
        query_text = canonical_profile_text(name, profile)
        vector = _embed(account_id, token, query_text)
        matches = _query(account_id, token, vector, top_k)
        accepted = []
        rejected = []
        for match in matches:
            similarity = float(match.get("score") or 0)
            metadata = match.get("metadata") or {}
            event_id = str(metadata.get("event_id") or match.get("id") or "")
            row = rows.get(event_id)
            if similarity < min_similarity:
                rejected.append({"event_id": event_id, "score": similarity, "reason": "below similarity threshold"})
                continue
            if row is None:
                rejected.append({"event_id": event_id, "score": similarity, "reason": "event missing from current state"})
                continue
            item = _semantic_item(row, ids_by_event.get(event_id, {}), profile, today, similarity)
            if item is None:
                allowed, reasons, _ = _hard_gate(row, profile, today)
                rejected.append({"event_id": event_id, "score": similarity, "reason": "; ".join(reasons) or "hard gate"})
                continue
            accepted.append(item)
        accepted.sort(key=lambda x: (-float(x.get("semantic_retrieval_score") or 0), -float(x.get("score") or 0), x["event_id"]))
        out[name] = {"query": query_text, "accepted": accepted, "rejected": rejected, "raw_matches": len(matches)}
    return out


def merge_into_feed(feed: dict[str, Any], discovery: dict[str, Any], per_profile: int = 30) -> dict[str, Any]:
    feed = json.loads(json.dumps(feed))
    combined: dict[str, dict[str, Any]] = {x["event_id"]: x for x in feed.get("items", [])}
    for name, result in discovery.items():
        profile_entry = feed.setdefault("profiles", {}).setdefault(name, {"label": name, "items": []})
        existing = {x["event_id"]: x for x in profile_entry.get("items", [])}
        for item in result["accepted"]:
            event_id = item["event_id"]
            if event_id in existing:
                existing[event_id]["semantic_retrieval_score"] = item["semantic_retrieval_score"]
                existing[event_id]["semantic_discovery"] = True
                existing[event_id]["discovery_method"] = "deterministic+vectorize"
            else:
                existing[event_id] = item
            current = combined.get(event_id)
            if current is None or float(item.get("score") or 0) > float(current.get("score") or 0):
                combined[event_id] = dict(existing[event_id])
            profiles = combined[event_id].setdefault("profiles", [])
            if name not in profiles:
                profiles.append(name)
            combined[event_id].setdefault("profile_scores", {})[name] = existing[event_id].get("score")
        profile_items = list(existing.values())
        profile_items.sort(key=lambda x: (-float(x.get("semantic_retrieval_score") or 0), -float(x.get("score") or 0), x["event_id"]))
        profile_entry["items"] = profile_items[:per_profile]
    items = list(combined.values())
    items.sort(key=lambda x: (-float(x.get("semantic_retrieval_score") or 0), -float(x.get("score") or 0), x["event_id"]))
    feed["items"] = items[:per_profile]
    feed["lanes"] = {
        lane: [x for x in items if x.get("lane") == lane][:per_profile]
        for lane in ("act_now", "market_intelligence", "policy_signals")
    }
    feed["semantic_discovery"] = {
        "provider": "cloudflare_vectorize",
        "model": MODEL,
        "index": INDEX,
        "profiles": {
            name: {
                "raw_matches": result["raw_matches"],
                "accepted": len(result["accepted"]),
                "rejected": len(result["rejected"]),
            }
            for name, result in discovery.items()
        },
    }
    return feed


def audit_report(feed_before: dict[str, Any], feed_after: dict[str, Any], discovery: dict[str, Any]) -> dict[str, Any]:
    before = {name: [x["event_id"] for x in data.get("items", [])[:10]] for name, data in feed_before.get("profiles", {}).items()}
    after = {name: [x["event_id"] for x in data.get("items", [])[:10]] for name, data in feed_after.get("profiles", {}).items()}
    profiles = {}
    for name in discovery:
        before_set = set(before.get(name, []))
        after_ids = after.get(name, [])
        promoted = [event_id for event_id in after_ids if event_id not in before_set]
        profiles[name] = {
            "deterministic_top10": before.get(name, []),
            "semantic_top10": after_ids,
            "new_in_top10": promoted,
            "new_in_top10_count": len(promoted),
            "accepted_candidates": len(discovery[name]["accepted"]),
            "rejected_candidates": len(discovery[name]["rejected"]),
            "top_rejections": discovery[name]["rejected"][:20],
        }
    return {"schema_version": 1, "profiles": profiles}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--feed", required=True)
    parser.add_argument("--audit", required=True)
    parser.add_argument("--as-of")
    parser.add_argument("--top-k", type=int, default=200)
    parser.add_argument("--min-similarity", type=float, default=0.50)
    args = parser.parse_args()
    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row
    feed_path = Path(args.feed)
    feed = json.loads(feed_path.read_text())
    as_of = args.as_of or feed.get("as_of") or dt.date.today().isoformat()
    discovery = discover(conn, as_of, top_k=args.top_k, min_similarity=args.min_similarity)
    merged = merge_into_feed(feed, discovery)
    feed_path.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
    audit = audit_report(feed, merged, discovery)
    audit_path = Path(args.audit)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n")
    print(json.dumps({
        "profiles": {
            name: {
                "accepted": len(result["accepted"]),
                "rejected": len(result["rejected"]),
                "new_top10": audit["profiles"][name]["new_in_top10_count"],
            }
            for name, result in discovery.items()
        }
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
