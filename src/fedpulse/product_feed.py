"""Reader-facing enrichment for FedPulse opportunity output.

This layer keeps source facts and analysis distinct. Deterministic evidence remains the
truth layer; semantic and optional AI signals only affect ordering and explanation.
"""
from __future__ import annotations

import os
from collections import defaultdict

from .ai_reranker import rerank as ai_rerank
from .opportunities import load_profiles
from .semantic import rerank_semantic


def _evidence_rows(item: dict) -> list[dict]:
    rows: list[dict] = []
    if item.get("stage"):
        rows.append({"type": "stage", "label": "Stage", "value": item["stage"]})
    if item.get("event_date"):
        rows.append({"type": "date", "label": "Official date", "value": item["event_date"]})
    if item.get("days_to_close") is not None:
        days = int(item["days_to_close"])
        rows.append({"type": "deadline", "label": "Response window", "value": "closes today" if days == 0 else f"{days} days remaining"})
    if item.get("amount") is not None:
        rows.append({"type": "amount", "label": "Value", "value": item["amount"], "currency": item.get("currency") or "USD"})
    ids = item.get("identifiers") or {}
    for namespace, label in (("naics", "NAICS"), ("solicitation", "Solicitation"), ("grants_opportunity", "Opportunity"), ("rin", "RIN"), ("award", "Award"), ("bill", "Bill")):
        values = ids.get(namespace) or []
        if values:
            rows.append({"type": namespace, "label": label, "value": ", ".join(str(x) for x in values[:3])})
    for reason in item.get("reasons") or []:
        if reason.startswith("geography:"):
            rows.append({"type": "geography", "label": "Geography", "value": reason.split(":", 1)[1].strip()})
        elif reason.startswith("agency:"):
            rows.append({"type": "agency", "label": "Agency match", "value": reason.split(":", 1)[1].strip()})
    # Keep the compact UI useful rather than exhaustive.
    seen = set()
    deduped = []
    for row in rows:
        key = (row.get("type"), str(row.get("value")))
        if key not in seen:
            seen.add(key)
            deduped.append(row)
    return deduped[:8]


def _related_actions(conn, event_id: str, limit: int = 4) -> list[dict]:
    if not event_id:
        return []
    rows = conn.execute(
        """SELECT e.event_id,e.source,e.kind,e.stage,e.title,e.agency,e.event_date,e.official_url,
                  ge.relationship,ge.method,ge.confidence
           FROM government_edges ge
           JOIN government_events e
             ON e.event_id = CASE WHEN ge.from_event_id=? THEN ge.to_event_id ELSE ge.from_event_id END
           WHERE ge.from_event_id=? OR ge.to_event_id=?
           ORDER BY COALESCE(e.event_date,'') DESC
           LIMIT ?""",
        (event_id, event_id, event_id, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def enrich_opportunities_payload(conn, payload: dict) -> dict:
    """Add semantic ordering, optional AI analysis, evidence, and related actions."""
    profiles = load_profiles()
    by_id: dict[str, dict] = {str(x.get("event_id")): dict(x) for x in payload.get("items") or [] if x.get("event_id")}
    semantic_matches: dict[str, dict[str, float]] = defaultdict(dict)
    ai_by_event: dict[str, dict] = {}

    # Work from the already deterministic-eligible profile sets. Semantic ranking may
    # reorder those candidates but may not create facts or bypass hard eligibility.
    for profile_name, profile_block in (payload.get("profiles") or {}).items():
        profile = profiles.get(profile_name)
        if not profile:
            continue
        candidates = [dict(x) for x in profile_block.get("items") or []]
        semantic = rerank_semantic(candidates, profile, limit=len(candidates) or 1)
        for rank, row in enumerate(semantic, 1):
            event_id = str(row.get("event_id") or "")
            if not event_id:
                continue
            semantic_matches[event_id][profile_name] = float(row.get("semantic_retrieval_score") or 0)
            if event_id in by_id:
                by_id[event_id].setdefault("semantic_ranks", {})[profile_name] = rank
        if os.getenv("FEDPULSE_AI_ENABLED", "0").lower() in {"1", "true", "yes"}:
            ai_rows = ai_rerank(semantic[:30], profile_name, profile)
            for row in ai_rows:
                event_id = str(row.get("event_id") or "")
                if not event_id:
                    continue
                current = ai_by_event.get(event_id)
                score = float(row.get("hybrid_score", row.get("score") or 0))
                if current is None or score > float(current.get("hybrid_score", current.get("score") or 0)):
                    ai_by_event[event_id] = row

    for event_id, item in by_id.items():
        matches = semantic_matches.get(event_id, {})
        item["semantic_matches"] = matches
        item["semantic_score"] = round(max(matches.values()), 4) if matches else 0.0
        item["evidence_summary"] = _evidence_rows(item)
        item["related_actions"] = _related_actions(conn, event_id)
        ai_row = ai_by_event.get(event_id)
        if ai_row:
            item["ai"] = ai_row.get("ai", {})
            item["ai_adjustment"] = ai_row.get("ai_adjustment", 0)
            item["hybrid_score"] = ai_row.get("hybrid_score", item.get("score"))
        else:
            item["ai"] = {"enabled": False, "status": "disabled"}
            item["ai_adjustment"] = 0
            item["hybrid_score"] = item.get("score")

    enriched = list(by_id.values())
    ai_enabled = any((x.get("ai") or {}).get("enabled") for x in enriched)
    enriched.sort(key=lambda x: (
        -float(x.get("hybrid_score") or 0),
        -float(x.get("semantic_score") or 0),
        -float(x.get("score") or 0),
        str(x.get("event_id") or ""),
    ))
    payload["items"] = enriched
    payload["lanes"] = {
        key: [x for x in enriched if x.get("lane") == key]
        for key in ("act_now", "market_intelligence", "policy_signals")
    }
    payload["ranking"] = {
        "mode": "hybrid" if ai_enabled else "semantic_plus_deterministic",
        "deterministic_eligibility": True,
        "semantic_rerank": True,
        "semantic_provider": "local_fallback",
        "ai_enabled": ai_enabled,
        "ai_role": "evidence-bound analyst and skeptic" if ai_enabled else None,
    }
    return payload
