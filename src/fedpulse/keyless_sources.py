"""Orchestrate FedPulse v0.4 zero-key government sources.

Each source has its own health/result so a failure never masquerades as a healthy
source and never prevents the core Federal Register snapshot from publishing.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import Callable

from . import congress_bulk_client, grants_client, oira_meetings_client, reginfo_client, sam_opportunities_client, usaspending_client
from .action_graph import GovernmentEvent, link_exact_identifiers, set_cursor, upsert_events


def _reginfo_event(doc: reginfo_client.RegInfoDocument) -> GovernmentEvent | None:
    if not doc.rin: return None
    date = doc.received_date or doc.concluded_date or doc.publication_date
    source_id = ":".join(x for x in (doc.rin, date, doc.stage, doc.status) if x) or doc.rin
    if doc.source == "unified_agenda": kind = "regulatory_plan"
    else: kind = "oira_review"
    if doc.source == "oira_pending": stage = "oira_pending"
    elif doc.source == "oira_completed_30": stage = "oira_completed"
    else: stage = doc.stage or doc.status or "agenda"
    payload = asdict(doc)
    return GovernmentEvent(
        source=doc.source, source_id=source_id, kind=kind, stage=stage, title=doc.title,
        agency=doc.agency, event_date=date, official_url=doc.source_url,
        identifiers=(("rin", doc.rin),), payload=payload, content_sha256=doc.raw_sha256,
    )


def mirror_federal_register(conn: sqlite3.Connection) -> int:
    """Project FR rows carrying RINs into the action graph without duplicating storage."""
    events = []
    for row in conn.execute("SELECT * FROM records WHERE source='fr' ORDER BY publication_date DESC"):
        raw = json.loads(row["raw_json"] or "{}")
        rins = [str(x).strip() for x in (raw.get("regulation_id_numbers") or []) if str(x).strip()]
        if not rins: continue
        identifiers = [("fr_document", row["id"].removeprefix("fr:"))] + [("rin", rin) for rin in rins]
        events.append(GovernmentEvent(
            source="federal_register", source_id=row["id"].removeprefix("fr:"), kind="regulatory_publication",
            stage=row["doc_type"], title=row["title"], agency=row["canonical_agency_name"] or row["agency"],
            event_date=row["publication_date"], official_url=row["url"], identifiers=tuple(identifiers),
            payload={"record_id": row["id"], "rins": rins, "docket_ids": raw.get("docket_ids") or []},
        ))
    return upsert_events(conn, events)


def _run_source(conn: sqlite3.Connection, name: str, loader: Callable[[], list[GovernmentEvent]]) -> dict:
    try:
        events = loader()
        conn.execute("SAVEPOINT keyless_source")
        count = upsert_events(conn, events)
        set_cursor(conn, name, str(count), detail=f"events={count}")
        conn.execute("RELEASE keyless_source")
        conn.commit()
        return {"status": "success", "events": count}
    except Exception as exc:
        try: conn.execute("ROLLBACK TO keyless_source"); conn.execute("RELEASE keyless_source")
        except sqlite3.Error: pass
        conn.rollback()
        return {"status": "failure", "events": 0, "error": str(exc)[:500]}


def sync_all(conn: sqlite3.Connection, *, include_bulk: bool = True, oira_meeting_rin_limit: int = 40, congress_file_limit: int = 100) -> dict:
    """Sync the complete zero-key source family and return per-source results."""
    results = {}
    results["federal_register_graph"] = _run_source(conn, "federal_register_graph", lambda: [])
    try:
        count = mirror_federal_register(conn); conn.commit()
        results["federal_register_graph"] = {"status": "success", "events": count}
    except Exception as exc:
        conn.rollback(); results["federal_register_graph"] = {"status": "failure", "events": 0, "error": str(exc)[:500]}

    def reginfo_loader():
        docs = reginfo_client.pull_oira_pending() + reginfo_client.pull_oira_completed_30() + reginfo_client.pull_unified_agenda()
        return [e for e in (_reginfo_event(d) for d in docs) if e]
    results["reginfo"] = _run_source(conn, "reginfo", reginfo_loader)

    def meeting_loader():
        rins = [r[0] for r in conn.execute(
            "SELECT DISTINCT value FROM government_identifiers WHERE namespace='rin' ORDER BY value LIMIT ?",
            (oira_meeting_rin_limit,),
        )]
        out = []
        for rin in rins:
            out.extend(oira_meetings_client.pull_for_rin(rin))
        return out
    results["oira_meetings"] = _run_source(conn, "oira_meetings", meeting_loader)

    if include_bulk:
        def grants_loader():
            url, digest, events = grants_client.pull_latest(); set_cursor(conn, "grants", url, digest, f"events={len(events)}"); return events
        results["grants"] = _run_source(conn, "grants", grants_loader)

        def sam_loader():
            url, digest, events = sam_opportunities_client.pull_current(); set_cursor(conn, "sam_opportunities", url, digest, f"events={len(events)}"); return events
        results["sam_opportunities"] = _run_source(conn, "sam_opportunities", sam_loader)
    else:
        results["grants"] = {"status": "skipped", "events": 0}
        results["sam_opportunities"] = {"status": "skipped", "events": 0}

    results["usaspending"] = _run_source(conn, "usaspending", lambda: usaspending_client.pull_recent_awards(days=3))
    results["bill_status"] = _run_source(conn, "bill_status", lambda: congress_bulk_client.pull_recent_updates(max_files=congress_file_limit))

    try:
        edges = link_exact_identifiers(conn); conn.commit()
    except Exception as exc:
        conn.rollback(); edges = 0; results["graph_linking"] = {"status": "failure", "error": str(exc)[:500]}
    else:
        results["graph_linking"] = {"status": "success", "edges_created": edges}
    return results
