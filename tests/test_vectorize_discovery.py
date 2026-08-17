import datetime as dt
import json
import sqlite3

from scripts.vectorize_discovery import _hard_gate, merge_into_feed


def _row(payload, *, event_date="2026-08-16", kind="contract_opportunity"):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE x (
        event_id TEXT, source TEXT, kind TEXT, stage TEXT, title TEXT, agency TEXT,
        event_date TEXT, amount REAL, currency TEXT, official_url TEXT,
        first_seen TEXT, last_seen TEXT, payload_json TEXT
        )"""
    )
    conn.execute(
        "INSERT INTO x VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "evt-1", "sam_opportunity", kind, "Sources Sought", "Roof repair",
            "Department of Veterans Affairs", event_date, 100000, "USD", "https://example.gov",
            event_date, event_date, json.dumps(payload),
        ),
    )
    return conn.execute("SELECT * FROM x").fetchone()


def test_hard_gate_requires_proven_geography():
    profile = {"lookback_days": 7, "require_geography": True, "geographies": ["seattle", "washington"]}
    row = _row({"row": {"PopCity": "Kigali", "PopState": ""}})
    allowed, reasons, _ = _hard_gate(row, profile, dt.date(2026, 8, 16))
    assert not allowed
    assert "required geography not proven" in reasons


def test_hard_gate_accepts_place_of_performance():
    profile = {"lookback_days": 7, "require_geography": True, "geographies": ["tacoma", "washington"]}
    row = _row({"row": {"PopCity": "Tacoma", "PopState": "WA", "ResponseDeadLine": "2026-08-25"}})
    allowed, reasons, days = _hard_gate(row, profile, dt.date(2026, 8, 16))
    assert allowed
    assert days == 9
    assert any("tacoma" in reason.lower() for reason in reasons)


def test_merge_adds_vector_only_candidate_without_dropping_deterministic():
    feed = {
        "profiles": {"default": {"label": "Construction", "items": [{"event_id": "det", "score": 90, "lane": "act_now"}]}},
        "items": [{"event_id": "det", "score": 90, "lane": "act_now", "profiles": ["default"], "profile_scores": {"default": 90}}],
        "lanes": {"act_now": [], "market_intelligence": [], "policy_signals": []},
    }
    discovery = {
        "default": {
            "raw_matches": 2,
            "rejected": [],
            "accepted": [{
                "event_id": "sem", "score": 70, "lane": "act_now",
                "semantic_retrieval_score": 0.91, "semantic_discovery": True,
                "discovery_method": "vectorize",
            }],
        }
    }
    merged = merge_into_feed(feed, discovery, per_profile=30)
    ids = {item["event_id"] for item in merged["profiles"]["default"]["items"]}
    assert ids == {"det", "sem"}
    assert merged["semantic_discovery"]["profiles"]["default"]["accepted"] == 1
