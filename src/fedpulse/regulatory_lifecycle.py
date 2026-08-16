"""Deterministic docket lifecycle synthesis from keyless Federal Register evidence."""
from __future__ import annotations

import json
import sqlite3
from collections import defaultdict


def infer_stage(doc_type: str | None) -> str:
    typ = (doc_type or "").strip().lower()
    if typ in {"proposed_rule", "proposed rule"} or "proposed" in typ:
        return "proposal_published"
    if typ in {"rule", "final_rule", "final rule"} or "final" in typ:
        return "final_published"
    if "notice" in typ:
        return "notice_activity"
    return "docket_activity"


def build_lifecycles(conn: sqlite3.Connection, as_of: str) -> list[dict]:
    """Build one lifecycle per public docket id present in Federal Register metadata."""
    rows = conn.execute(
        """SELECT id,title,doc_type,publication_date,url,canonical_agency_id,
                  canonical_agency_name,agency,raw_json
           FROM records
           WHERE source='fr' AND publication_date <= ?
           ORDER BY publication_date,id""",
        (as_of,),
    ).fetchall()
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        raw = json.loads(row["raw_json"] or "{}")
        for docket_id in raw.get("docket_ids") or []:
            docket_id = str(docket_id).strip()
            if not docket_id:
                continue
            grouped[docket_id].append({
                "record_id": row["id"],
                "title": row["title"],
                "document_type": row["doc_type"],
                "publication_date": row["publication_date"],
                "stage": infer_stage(row["doc_type"]),
                "official_url": row["url"],
            })
    priority = {"final_published": 4, "proposal_published": 3, "notice_activity": 2, "docket_activity": 1}
    out: list[dict] = []
    for docket_id, events in grouped.items():
        current = max(events, key=lambda e: (priority.get(e["stage"], 0), e.get("publication_date") or ""))
        first = min((e["publication_date"] for e in events if e.get("publication_date")), default=None)
        last = max((e["publication_date"] for e in events if e.get("publication_date")), default=None)
        agency = next((r for r in reversed(rows) if r["id"] in {e["record_id"] for e in events}), None)
        lifecycle = {
            "docket_id": docket_id,
            "stage": current["stage"],
            "event_count": len(events),
            "first_publication_date": first,
            "last_publication_date": last,
            "agency_id": agency["canonical_agency_id"] if agency else None,
            "agency": (agency["canonical_agency_name"] or agency["agency"]) if agency else None,
            "regulations_url": f"https://www.regulations.gov/docket/{docket_id}",
            "events": events,
            "source_basis": "Federal Register docket_ids; no API key required",
        }
        out.append(lifecycle)
        conn.execute(
            """INSERT INTO regulatory_lifecycles(docket_id,stage,first_seen,last_seen,payload_json)
               VALUES (?,?,datetime('now'),datetime('now'),?)
               ON CONFLICT(docket_id) DO UPDATE SET stage=excluded.stage,last_seen=datetime('now'),payload_json=excluded.payload_json""",
            (docket_id, lifecycle["stage"], json.dumps(lifecycle, ensure_ascii=False)),
        )
    return sorted(out, key=lambda x: (x.get("last_publication_date") or "", x["docket_id"]), reverse=True)
