from __future__ import annotations

import os
import sqlite3
import unittest
from unittest.mock import patch

from fedpulse.product_feed import enrich_opportunities_payload


class ProductFeedTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(
            """
            CREATE TABLE government_events (
              event_id TEXT PRIMARY KEY, source TEXT, kind TEXT, stage TEXT, title TEXT,
              agency TEXT, event_date TEXT, official_url TEXT
            );
            CREATE TABLE government_edges (
              from_event_id TEXT, to_event_id TEXT, relationship TEXT, method TEXT,
              confidence TEXT
            );
            """
        )
        self.conn.execute(
            "INSERT INTO government_events VALUES (?,?,?,?,?,?,?,?)",
            ("sam:related", "sam", "contract_opportunity", "award", "Related award", "GSA", "2026-08-15", "https://sam.gov/related"),
        )
        self.conn.execute(
            "INSERT INTO government_edges VALUES (?,?,?,?,?)",
            ("sam:1", "sam:related", "same_government_action", "exact:solicitation", "high"),
        )

    def tearDown(self):
        self.conn.close()

    def payload(self):
        item = {
            "event_id": "sam:1", "source": "sam", "kind": "contract_opportunity",
            "lane": "act_now", "stage": "Sources Sought", "title": "Roof replacement",
            "agency": "GSA", "event_date": "2026-08-16", "amount": 250000,
            "currency": "USD", "official_url": "https://sam.gov/1", "score": 80,
            "score_components": {"freshness": 28, "relevance": 30}, "edge": "early",
            "reasons": ["geography: Tacoma", "NAICS: 238160", "sources-sought signal"],
            "days_to_close": 12, "identifiers": {"naics": ["238160"], "solicitation": ["ABC-1"]},
            "profiles": ["default"], "profile_scores": {"default": 80},
        }
        return {
            "profiles": {"default": {"label": "Construction / AEC / Washington", "items": [item]}},
            "items": [item], "lanes": {"act_now": [item], "market_intelligence": [], "policy_signals": []},
        }

    @patch.dict(os.environ, {"FEDPULSE_AI_ENABLED": "0"}, clear=False)
    def test_adds_evidence_semantic_and_related_actions_without_ai(self):
        result = enrich_opportunities_payload(self.conn, self.payload())
        item = result["items"][0]
        labels = {row["label"] for row in item["evidence_summary"]}
        self.assertIn("Stage", labels)
        self.assertIn("Geography", labels)
        self.assertIn("NAICS", labels)
        self.assertEqual(item["ai"]["status"], "disabled")
        self.assertIn("semantic_score", item)
        self.assertEqual(item["related_actions"][0]["event_id"], "sam:related")
        self.assertEqual(result["ranking"]["mode"], "semantic_plus_deterministic")
        self.assertEqual(result["lanes"]["act_now"][0]["event_id"], "sam:1")


if __name__ == "__main__":
    unittest.main()
