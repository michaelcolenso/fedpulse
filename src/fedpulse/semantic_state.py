"""Persistent state for incremental semantic embedding.

The nightly job stores content fingerprints in the same SQLite database that is
round-tripped through R2. A fingerprint is committed only after the corresponding
Vectorize upsert succeeds, so failed uploads are retried on the next run.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

TABLE = "semantic_embedding_state"


@dataclass(frozen=True)
class EmbeddingState:
    event_id: str
    content_hash: str
    model: str


def content_fingerprint(text: str, model: str) -> str:
    """Hash the exact canonical embedding text plus the embedding model identity."""
    payload = f"{model}\0{text}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            event_id TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            model TEXT NOT NULL,
            embedded_at TEXT NOT NULL
        )
        """
    )


def changed_states(
    conn: sqlite3.Connection,
    candidates: Iterable[EmbeddingState],
) -> list[EmbeddingState]:
    """Return only new records or records whose canonical fingerprint changed."""
    ensure_schema(conn)
    existing = {
        str(row[0]): (str(row[1]), str(row[2]))
        for row in conn.execute(f"SELECT event_id, content_hash, model FROM {TABLE}")
    }
    return [
        candidate
        for candidate in candidates
        if existing.get(candidate.event_id)
        != (candidate.content_hash, candidate.model)
    ]


def apply_update_budget(
    states: Iterable[EmbeddingState],
    max_updates: int | None,
) -> tuple[list[EmbeddingState], int]:
    """Bound per-run embedding work without limiting corpus eligibility.

    ``max_updates`` is a throughput guard only. All eligible records are still
    fingerprinted and compared each run; overflow remains uncommitted and therefore
    stays in the changed backlog for the next run.
    """
    rows = list(states)
    if not max_updates or max_updates <= 0 or len(rows) <= max_updates:
        return rows, 0
    return rows[:max_updates], len(rows) - max_updates


def commit_states(
    conn: sqlite3.Connection,
    states: Iterable[EmbeddingState],
    *,
    embedded_at: str | None = None,
) -> int:
    """Persist successful Vectorize upserts and return the number committed."""
    ensure_schema(conn)
    rows = list(states)
    if not rows:
        return 0
    timestamp = embedded_at or datetime.now(timezone.utc).isoformat()
    conn.executemany(
        f"""
        INSERT INTO {TABLE} (event_id, content_hash, model, embedded_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(event_id) DO UPDATE SET
            content_hash = excluded.content_hash,
            model = excluded.model,
            embedded_at = excluded.embedded_at
        """,
        [(row.event_id, row.content_hash, row.model, timestamp) for row in rows],
    )
    conn.commit()
    return len(rows)
