from __future__ import annotations

import sqlite3
import unittest

from fedpulse.semantic_state import (
    EmbeddingState,
    apply_update_budget,
    changed_states,
    commit_states,
    content_fingerprint,
)


class SemanticStateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = sqlite3.connect(":memory:")

    def tearDown(self) -> None:
        self.conn.close()

    def test_fingerprint_is_stable_for_same_canonical_content(self) -> None:
        left = content_fingerprint("Title: Bridge repair", "model-a")
        right = content_fingerprint("Title: Bridge repair", "model-a")
        self.assertEqual(left, right)

    def test_fingerprint_changes_when_content_changes(self) -> None:
        left = content_fingerprint("Title: Bridge repair", "model-a")
        right = content_fingerprint("Title: Bridge replacement", "model-a")
        self.assertNotEqual(left, right)

    def test_fingerprint_changes_when_model_changes(self) -> None:
        left = content_fingerprint("Title: Bridge repair", "model-a")
        right = content_fingerprint("Title: Bridge repair", "model-b")
        self.assertNotEqual(left, right)

    def test_only_new_or_changed_records_are_selected(self) -> None:
        original = EmbeddingState("evt-1", "hash-a", "model-a")
        commit_states(self.conn, [original], embedded_at="2026-08-16T00:00:00+00:00")

        candidates = [
            EmbeddingState("evt-1", "hash-a", "model-a"),
            EmbeddingState("evt-2", "hash-b", "model-a"),
            EmbeddingState("evt-3", "hash-c", "model-a"),
        ]
        changed = changed_states(self.conn, candidates)
        self.assertEqual([state.event_id for state in changed], ["evt-2", "evt-3"])

    def test_changed_hash_is_selected_and_commit_updates_state(self) -> None:
        commit_states(
            self.conn,
            [EmbeddingState("evt-1", "hash-a", "model-a")],
            embedded_at="2026-08-16T00:00:00+00:00",
        )
        updated = EmbeddingState("evt-1", "hash-b", "model-a")
        self.assertEqual(changed_states(self.conn, [updated]), [updated])

        commit_states(
            self.conn,
            [updated],
            embedded_at="2026-08-17T00:00:00+00:00",
        )
        self.assertEqual(changed_states(self.conn, [updated]), [])

    def test_model_change_forces_reembedding(self) -> None:
        commit_states(
            self.conn,
            [EmbeddingState("evt-1", "hash-a", "model-a")],
            embedded_at="2026-08-16T00:00:00+00:00",
        )
        updated = EmbeddingState("evt-1", "hash-a", "model-b")
        self.assertEqual(changed_states(self.conn, [updated]), [updated])

    def test_update_budget_defers_overflow_without_dropping_it(self) -> None:
        states = [
            EmbeddingState(f"evt-{index}", f"hash-{index}", "model-a")
            for index in range(5)
        ]
        scheduled, deferred = apply_update_budget(states, 2)
        self.assertEqual([state.event_id for state in scheduled], ["evt-0", "evt-1"])
        self.assertEqual(deferred, 3)

        # Only successful scheduled rows are committed; overflow remains changed.
        commit_states(self.conn, scheduled, embedded_at="2026-08-17T00:00:00+00:00")
        remaining = changed_states(self.conn, states)
        self.assertEqual(
            [state.event_id for state in remaining],
            ["evt-2", "evt-3", "evt-4"],
        )

    def test_zero_update_budget_means_unbounded(self) -> None:
        states = [
            EmbeddingState(f"evt-{index}", f"hash-{index}", "model-a")
            for index in range(3)
        ]
        scheduled, deferred = apply_update_budget(states, 0)
        self.assertEqual(scheduled, states)
        self.assertEqual(deferred, 0)


if __name__ == "__main__":
    unittest.main()
