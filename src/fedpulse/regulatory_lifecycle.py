"""Deterministic Federal Register + Regulations.gov lifecycle synthesis."""
from __future__ import annotations

import datetime as dt
import json
import sqlite3
from collections import defaultdict
from typing import Iterable


def upsert_regulations_document(conn: sqlite3.Connection, row: dict) -> None:
    conn.execute(
        """INSERT INTO regulations_documents
        (document_id,docket_id,agency_id,document_type,title,posted_date,last_modified_date,
         comment_end_date,withdrawn,object_id,fr_doc_number,raw_json,updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(document_id) DO UPDATE SET
          docket_id=excluded.docket_id,agency_id=excluded.agency_id,document_type=excluded.document_type,
          title=excluded.title,posted_date=excluded.posted_date,last_modified_date=excluded.last_modified_date,
          comment_end_date=excluded.comment_end_date,withdrawn=excluded.withdrawn,object_id=excluded.object_id,
          fr_doc_number=excluded.fr_doc_number,raw_json=excluded.raw_json,updated_at=datetime('now')""",
        (
            row.get("document_id"), row.get("docket_id"), row.get("agency_id"), row.get("document_type"),
            row.get("title"), row.get("posted_date"), row.get("last_modified_date"), row.get("comment_end_date"),
            1 if row.get("withdrawn") else 0, row.get("object_id"), row.get("fr_doc_number"),
            json.dumps(row.get("raw_json") or {}, ensure_ascii=False)[:1_000_000],
        ),
    )


def link_fr_documents(conn: sqlite3.Connection) -> int:
    """Link Regulations.gov docs to FR rows by explicit FR doc number or shared docket id."""
    linked = 0
    regs = conn.execute("SELECT document_id,docket_id,fr_doc_number FROM regulations_documents").fetchall()
    fr_rows = conn.execute("SELECT id,raw_json FROM records WHERE source='fr'").fetchall()
    docket_to_fr: dict[str, set[str]] = defaultdict(set)
    for row in fr_rows:
        raw = json.loads(row["raw_json"] or "{}")
        for docket_id in raw.get("docket_ids") or []:
            docket_to_fr[str(docket_id)].add(row["id"])
    for reg in regs:
        candidates: set[str] = set()
        if reg["fr_doc_number"]:
            candidates.add(f"fr:{reg['fr_doc_number']}")
        if reg["docket_id"]:
            candidates.update(docket_to_fr.get(reg["docket_id"], set()))
        for fr_id in candidates:
            exists = conn.execute("SELECT 1 FROM records WHERE id=?", (fr_id,)).fetchone()
            if not exists:
                continue
            cur = conn.execute(
                "INSERT OR IGNORE INTO regulations_fr_links(document_id,fr_record_id,link_method) VALUES (?,?,?)",
                (reg["document_id"], fr_id, "fr_doc_number" if reg["fr_doc_number"] and fr_id == f"fr:{reg['fr_doc_number']}" else "docket_id"),
            )
            linked += cur.rowcount
    return linked


def infer_stage(document_type: str | None, *, withdrawn: bool = False, comment_end_date: str | None = None, as_of: str | None = None) -> str:
    if withdrawn:
        return "withdrawn"
    typ = (document_type or "").strip().lower()
    if "proposed" in typ:
        if comment_end_date and as_of and comment_end_date[:10] < as_of:
            return "comments_closed"
        return "proposal_open"
    if typ == "rule" or "final" in typ:
        return "final_published"
    if "support" in typ:
        return "supporting_material"
    return "docket_activity"


def build_lifecycles(conn: sqlite3.Connection, as_of: str) -> list[dict]:
    """Build one lifecycle per docket from posted Regulations.gov evidence."""
    rows = conn.execute(
        """SELECT d.*, group_concat(l.fr_record_id) AS fr_record_ids
           FROM regulations_documents d
           LEFT JOIN regulations_fr_links l ON l.document_id=d.document_id
           WHERE d.docket_id IS NOT NULL
           GROUP BY d.document_id
           ORDER BY d.docket_id,d.posted_date,d.document_id"""
    ).fetchall()
    grouped: dict[str, list] = defaultdict(list)
    for row in rows:
        grouped[row["docket_id"]].append(row)
    out: list[dict] = []
    for docket_id, docs in grouped.items():
        events = []
        for row in docs:
            events.append({
                "document_id": row["document_id"],
                "title": row["title"],
                "document_type": row["document_type"],
                "posted_date": row["posted_date"],
                "comment_end_date": row["comment_end_date"],
                "stage": infer_stage(row["document_type"], withdrawn=bool(row["withdrawn"]), comment_end_date=row["comment_end_date"], as_of=as_of),
                "regulations_url": f"https://www.regulations.gov/document/{row['document_id']}",
                "fr_record_ids": [x for x in (row["fr_record_ids"] or "").split(",") if x],
            })
        stage_priority = {"withdrawn": 6, "final_published": 5, "comments_closed": 4, "proposal_open": 3, "supporting_material": 2, "docket_activity": 1}
        current = max(events, key=lambda e: (stage_priority.get(e["stage"], 0), e.get("posted_date") or ""))
        lifecycle = {
            "docket_id": docket_id,
            "agency_id": next((r["agency_id"] for r in reversed(docs) if r["agency_id"]), None),
            "title": next((r["title"] for r in docs if r["title"]), docket_id),
            "stage": current["stage"],
            "event_count": len(events),
            "first_posted_date": min((e["posted_date"] for e in events if e["posted_date"]), default=None),
            "last_posted_date": max((e["posted_date"] for e in events if e["posted_date"]), default=None),
            "events": events,
        }
        out.append(lifecycle)
        conn.execute(
            """INSERT INTO regulatory_lifecycles(docket_id,stage,first_seen,last_seen,payload_json)
               VALUES (?,?,datetime('now'),datetime('now'),?)
               ON CONFLICT(docket_id) DO UPDATE SET stage=excluded.stage,last_seen=datetime('now'),payload_json=excluded.payload_json""",
            (docket_id, lifecycle["stage"], json.dumps(lifecycle, ensure_ascii=False)),
        )
    return sorted(out, key=lambda x: (x.get("last_posted_date") or "", x["docket_id"]), reverse=True)
