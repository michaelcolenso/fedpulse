"""Unified government-action graph for zero-key FedPulse sources."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class GovernmentEvent:
    source: str
    source_id: str
    kind: str
    stage: str | None = None
    title: str | None = None
    agency: str | None = None
    event_date: str | None = None
    amount: float | None = None
    currency: str | None = None
    official_url: str | None = None
    identifiers: tuple[tuple[str, str], ...] = field(default_factory=tuple)
    payload: dict = field(default_factory=dict)
    content_sha256: str | None = None

    @property
    def event_id(self) -> str:
        return f"{self.source}:{self.source_id}"


def payload_hash(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


_EVENT_UPSERT = """INSERT INTO government_events
(event_id,source,source_id,kind,stage,title,agency,event_date,amount,currency,official_url,payload_json,content_sha256)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(event_id) DO UPDATE SET
  kind=excluded.kind,stage=excluded.stage,title=excluded.title,agency=excluded.agency,
  event_date=excluded.event_date,amount=excluded.amount,currency=excluded.currency,
  official_url=excluded.official_url,payload_json=excluded.payload_json,
  content_sha256=excluded.content_sha256,last_seen=datetime('now')"""


def _event_row(event: GovernmentEvent) -> tuple:
    return (
        event.event_id,event.source,event.source_id,event.kind,event.stage,event.title,event.agency,
        event.event_date,event.amount,event.currency,event.official_url,
        json.dumps(event.payload,ensure_ascii=False)[:1_000_000],event.content_sha256 or payload_hash(event.payload),
    )


def upsert_event(conn: sqlite3.Connection, event: GovernmentEvent) -> None:
    conn.execute(_EVENT_UPSERT,_event_row(event))
    conn.execute("DELETE FROM government_identifiers WHERE event_id=?",(event.event_id,))
    identifiers=[(event.event_id,str(namespace),str(value).strip()) for namespace,value in event.identifiers if str(value or "").strip()]
    if identifiers:
        conn.executemany("INSERT OR IGNORE INTO government_identifiers(event_id,namespace,value) VALUES (?,?,?)",identifiers)


def upsert_events(conn: sqlite3.Connection, events: Iterable[GovernmentEvent], *, batch_size: int = 1000) -> int:
    """Bulk-upsert events and identifiers without per-row SQLite round trips."""
    batch=[]; count=0
    def flush(items):
        nonlocal count
        if not items:return
        conn.executemany(_EVENT_UPSERT,[_event_row(event) for event in items])
        ids=[event.event_id for event in items]
        # Stay comfortably below SQLite's host-parameter limit on older builds.
        for start in range(0,len(ids),400):
            chunk=ids[start:start+400]; placeholders=",".join("?" for _ in chunk)
            conn.execute(f"DELETE FROM government_identifiers WHERE event_id IN ({placeholders})",chunk)
        identifier_rows=[]
        for event in items:
            identifier_rows.extend((event.event_id,str(namespace),str(value).strip()) for namespace,value in event.identifiers if str(value or "").strip())
        if identifier_rows:
            conn.executemany("INSERT OR IGNORE INTO government_identifiers(event_id,namespace,value) VALUES (?,?,?)",identifier_rows)
        count+=len(items)
    for event in events:
        batch.append(event)
        if len(batch)>=batch_size:
            flush(batch);batch=[]
    flush(batch)
    return count


def link_exact_identifiers(conn: sqlite3.Connection) -> int:
    """Create deterministic edges for shared strong identifiers.

    Broad classification identifiers such as NAICS and Assistance Listing/CFDA are
    intentionally excluded: two awards in the same program are related, but they are
    not the same government action.
    """
    strong = {"rin", "grants_opportunity", "sam_notice", "solicitation", "award", "bill", "public_law", "fr_document"}
    rows = conn.execute(
        """SELECT namespace,value,group_concat(event_id) event_ids
           FROM government_identifiers
           GROUP BY namespace,value HAVING count(DISTINCT event_id) > 1"""
    ).fetchall()
    created = 0
    for row in rows:
        if row["namespace"] not in strong:
            continue
        ids = sorted(set((row["event_ids"] or "").split(",")))
        for i, left in enumerate(ids):
            for right in ids[i + 1:]:
                if not left or not right:
                    continue
                cur = conn.execute(
                    """INSERT OR IGNORE INTO government_edges
                    (from_event_id,to_event_id,relationship,method,confidence)
                    VALUES (?,?,?,?,?)""",
                    (left, right, "same_government_action", f"exact:{row['namespace']}", "high"),
                )
                created += cur.rowcount
    return created


def set_cursor(conn: sqlite3.Connection, source: str, cursor: str | None, digest: str | None = None, detail: str | None = None) -> None:
    conn.execute(
        """INSERT INTO source_cursors(source,cursor,content_sha256,last_success,detail)
        VALUES (?,?,?,datetime('now'),?)
        ON CONFLICT(source) DO UPDATE SET cursor=excluded.cursor,content_sha256=excluded.content_sha256,
        last_success=datetime('now'),detail=excluded.detail""",
        (source,cursor,digest,detail),
    )


def graph_summary(conn: sqlite3.Connection, limit: int = 100) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM government_events ORDER BY COALESCE(event_date,'') DESC,last_seen DESC LIMIT ?",
        (limit,),
    ).fetchall()
    out = []
    for row in rows:
        identifiers = [dict(x) for x in conn.execute(
            "SELECT namespace,value FROM government_identifiers WHERE event_id=? ORDER BY namespace,value",
            (row["event_id"],),
        )]
        edges = [dict(x) for x in conn.execute(
            """SELECT from_event_id,to_event_id,relationship,method,confidence FROM government_edges
               WHERE from_event_id=? OR to_event_id=? ORDER BY created_at""",
            (row["event_id"],row["event_id"]),
        )]
        item = dict(row)
        item["payload"] = json.loads(item.pop("payload_json") or "{}")
        item["identifiers"] = identifiers
        item["edges"] = edges
        out.append(item)
    return out
