"""Deterministic Federal Register regulatory-package detection and versioning."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Mapping, Sequence

from .taxonomy import AgencyIdentity, canonicalize_agency, classify_direction, coverage_tags, taxonomy_versions, watchlist_matches

@dataclass(frozen=True)
class EnrichedRecord:
    record_id: str
    source: str
    title: str
    raw_agency: str
    canonical_agency_id: str | None
    canonical_agency_name: str | None
    parent_id: str | None
    publication_date: date
    doc_type: str
    topics: tuple[str, ...]
    direction: str
    matched_phrases: tuple[dict[str, Any], ...]
    sectors: tuple[dict[str, Any], ...]
    url: str | None
    raw_metadata: dict[str, Any]
    watchlist: tuple[dict[str, Any], ...]


def _raw(row: Mapping[str, Any]) -> dict[str, Any]:
    value = row.get("raw_json") if hasattr(row, "get") else row["raw_json"]
    if isinstance(value, str):
        try: return json.loads(value)
        except json.JSONDecodeError: return {}
    return value or {}

def _topics(row: Mapping[str, Any]) -> tuple[str, ...]:
    value = row.get("subjects") or row.get("topics") or []
    if isinstance(value, str):
        try: value = json.loads(value)
        except json.JSONDecodeError: value = [value]
    return tuple(sorted({str(x) for x in value if x}))

def enrich_record(row: Mapping[str, Any]) -> EnrichedRecord:
    if not hasattr(row, "get"):
        row = dict(row)
    raw = _raw(row)
    source = str(row.get("source") or "fr")
    raw_agency = str(row.get("agency") or "")
    mapped = canonicalize_agency(source, raw_agency, raw)
    identity = AgencyIdentity(source, raw_agency, row.get("canonical_agency_id") or mapped.canonical_id, row.get("canonical_agency_name") or mapped.canonical_name, mapped.parent_id, "stored" if row.get("canonical_agency_id") else mapped.mapping_method)
    direction = classify_direction({**dict(row), **raw})
    sectors = coverage_tags({**dict(row), "subjects": _topics(row)}, identity)
    return EnrichedRecord(
        record_id=str(row["id"]), source=source, title=str(row.get("title") or ""), raw_agency=raw_agency,
        canonical_agency_id=identity.canonical_id, canonical_agency_name=identity.canonical_name,
        parent_id=identity.parent_id, publication_date=date.fromisoformat(str(row["publication_date"])),
        doc_type=str(row.get("doc_type") or "").strip().lower().replace("-", "_").replace(" ", "_"),
        topics=_topics(row), direction=direction["direction"], matched_phrases=tuple(direction["matched_phrases"]),
        sectors=tuple(sectors), url=row.get("url"), raw_metadata=raw,
        watchlist=tuple(watchlist_matches({**dict(row), "subjects": _topics(row)}, identity)),
    )

def _same_agency(a: EnrichedRecord, b: EnrichedRecord) -> bool:
    if a.canonical_agency_id and a.canonical_agency_id == b.canonical_agency_id: return True
    return bool(a.parent_id and a.parent_id == b.parent_id and a.canonical_agency_id and b.canonical_agency_id and a.canonical_agency_id != b.canonical_agency_id)

def _coherence(a: EnrichedRecord, b: EnrichedRecord) -> dict[str, Any]:
    topics = sorted(set(a.topics) & set(b.topics))
    sectors_a = {x["sector"] for x in a.sectors}; sectors_b = {x["sector"] for x in b.sectors}
    direction_sector = a.direction != "mixed_or_unknown" and a.direction == b.direction and sorted(sectors_a & sectors_b)
    return {"shared_topics": topics, "shared_direction": a.direction if direction_sector else None, "shared_sectors": sorted(sectors_a & sectors_b), "topic_coherent": bool(topics), "direction_sector_coherent": bool(direction_sector)}

def candidate_edges(records: Sequence[EnrichedRecord]) -> list[tuple[str, str, dict[str, Any]]]:
    ordered = sorted(records, key=lambda r: (r.publication_date, r.record_id))
    edges = []
    for i, a in enumerate(ordered):
        for b in ordered[i + 1:]:
            if b.publication_date - a.publication_date > timedelta(days=2): continue
            if not _same_agency(a, b): continue
            evidence = _coherence(a, b)
            if evidence["topic_coherent"] or evidence["direction_sector_coherent"]:
                edges.append((a.record_id, b.record_id, evidence))
    return edges

def _components(records: Sequence[EnrichedRecord], edges: Sequence[tuple[str, str, dict]]) -> list[list[EnrichedRecord]]:
    by_id = {r.record_id: r for r in records}; parent = {r.record_id: r.record_id for r in records}
    def find(x):
        while parent[x] != x: parent[x] = parent[parent[x]]; x = parent[x]
        return x
    def union(a, b):
        a, b = find(a), find(b)
        if a != b: parent[b] = a
    for a, b, _ in edges: union(a, b)
    groups: dict[str, list[EnrichedRecord]] = {}
    for r in records: groups.setdefault(find(r.record_id), []).append(r)
    return [sorted(v, key=lambda r: (r.publication_date, r.record_id)) for v in groups.values() if len(v) >= 2]

def bounded_components(records: Sequence[EnrichedRecord], edges: Sequence[tuple[str, str, dict]], max_span_days: int = 2) -> list[list[EnrichedRecord]]:
    result = []
    for component in _components(records, edges):
        current: list[EnrichedRecord] = []; start = None
        for record in component:
            if start is None or (record.publication_date - start).days <= max_span_days:
                current.append(record); start = start or record.publication_date
            else:
                if len(current) >= 2: result.extend(_coherent_partitions(current, max_span_days))
                current = [record]; start = record.publication_date
        if len(current) >= 2: result.extend(_coherent_partitions(current, max_span_days))
    return sorted(result, key=lambda c: (c[0].publication_date, c[0].record_id))

def _coherent_partitions(component: list[EnrichedRecord], max_span_days: int) -> list[list[EnrichedRecord]]:
    # Re-run coherence after date partition; a same-family/count batch stays out.
    if max((r.publication_date for r in component)) - min((r.publication_date for r in component)) > timedelta(days=max_span_days): return []
    by_id = {r.record_id: r for r in component}
    edges = candidate_edges(component)
    pieces = _components(component, edges)
    return [p for p in pieces if len(p) >= 2 and (p[-1].publication_date - p[0].publication_date).days <= max_span_days]

def _core_key(component: Sequence[EnrichedRecord]) -> str:
    topic_counts: dict[str, int] = {}
    for r in component:
        for t in r.topics: topic_counts[t] = topic_counts.get(t, 0) + 1
    majority = sorted(t for t, n in topic_counts.items() if n * 2 > len(component))
    if majority: basis = "topic:" + majority[0]
    else:
        dirs = [r.direction for r in component if r.direction != "mixed_or_unknown"]
        sectors = sorted(set.intersection(*[{x["sector"] for x in r.sectors} for r in component])) if component and all(r.sectors for r in component) else []
        basis = "direction:" + (max(set(dirs), key=dirs.count) if dirs else "mixed_or_unknown") + ":sector:" + (sectors[0] if sectors else "unknown")
    return hashlib.sha256(("package-core-v1|" + basis).encode()).hexdigest()[:12]

def _coordination(component: Sequence[EnrichedRecord]) -> dict[str, Any]:
    ids = sorted({r.canonical_agency_id for r in component if r.canonical_agency_id})
    parents = sorted({r.parent_id for r in component if r.parent_id})
    if len(component) == 1 and len(ids) == 1:
        return {"known": True, "coordination_agency_id": ids[0], "participating_agency_ids": ids}
    if len(ids) >= 2 and len(parents) == 1 and all(r.canonical_agency_id and r.parent_id == parents[0] for r in component):
        return {"known": True, "coordination_agency_id": parents[0], "participating_agency_ids": ids}
    if len(ids) == 1 and all(r.canonical_agency_id == ids[0] for r in component):
        return {"known": True, "coordination_agency_id": ids[0], "participating_agency_ids": ids}
    return {"known": False, "coordination_agency_id": None, "participating_agency_ids": ids}

def package_identity(component: Sequence[EnrichedRecord], prior_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    ordered = sorted(component, key=lambda r: (r.publication_date, r.record_id))
    coordination = _coordination(ordered)
    if prior_state and prior_state.get("package_id"):
        package_id = prior_state["package_id"]
    else:
        agency = coordination["coordination_agency_id"] or "unmapped"
        participants = "+".join(coordination["participating_agency_ids"])
        package_id = f"{agency}:{participants}:{ordered[0].publication_date.isoformat()}:{_core_key(ordered)}"
    core_key = prior_state.get("core_cluster_key") if prior_state else None
    return {"package_id": package_id, "core_cluster_key": core_key or _core_key(ordered), "agency_id": ordered[0].canonical_agency_id, "coordination_agency_id": coordination["coordination_agency_id"], "participating_agency_ids": coordination["participating_agency_ids"], "earliest_publication_date": ordered[0].publication_date.isoformat()}

def score_package(component: Sequence[EnrichedRecord], metrics: Mapping[str, Any] | None = None, watchlists: Any = None, prior_state: Mapping[str, Any] | None = None) -> dict[str, Any]:
    ordered = sorted(component, key=lambda r: (r.publication_date, r.record_id))
    identity = package_identity(ordered, prior_state)
    directions = [r.direction for r in ordered if r.direction != "mixed_or_unknown"]
    dominant = max(set(directions), key=directions.count) if directions else "mixed_or_unknown"
    direction_ratio = directions.count(dominant) / len(ordered) if ordered else 0
    topic_coherent = any(_coherence(a, b)["topic_coherent"] for i, a in enumerate(ordered) for b in ordered[i + 1:])
    dir_sector = any(_coherence(a, b)["direction_sector_coherent"] for i, a in enumerate(ordered) for b in ordered[i + 1:])
    coherence = topic_coherent or dir_sector
    both_two = len(ordered) != 2 or (all(_coherence(a, b)["topic_coherent"] and _coherence(a, b)["direction_sector_coherent"] for a, b in [(ordered[0], ordered[1])]))
    coordination = _coordination(ordered)
    known = coordination["known"]
    urls = all(bool(r.url) for r in ordered)
    if len(ordered) >= 3 and coherence and direction_ratio >= .6 and known and urls: confidence = "high"
    elif coherence and both_two and known and len(ordered) >= 2: confidence = "medium"
    else: confidence = "low"
    shared_topics = sorted(set.intersection(*(set(r.topics) for r in ordered))) if ordered and all(r.topics for r in ordered) else []
    matched = [p for r in ordered for p in r.matched_phrases]
    coverage = sorted({(x["sector"], x["source"], x["matched_value"]) for r in ordered for x in r.sectors})
    family_weight = max({"rule":3,"final_rule":3,"proposed_rule":2,"notice":1,"presidential_document":1}.get(r.doc_type, 0) for r in ordered) if ordered else 0
    components = {"record_count": min(3, max(0, len(ordered)-1)), "document_family": family_weight, "topic_cohesion": 2 if shared_topics else (1 if topic_coherent else 0), "direction_consistency": 2 if direction_ratio >= .8 else (1 if direction_ratio >= .6 else 0), "current_activity_anomaly": (metrics or {}).get("activity_anomaly", 0), "watchlist_match": min(3, sum(len(r.watchlist) for r in ordered)), "missing_evidence_penalty": -sum(1 for r in ordered if not r.url)}
    evidence = [{"record_id":r.record_id,"source":r.source,"title":r.title,"doc_type":r.doc_type,"publication_date":r.publication_date.isoformat(),"official_url":r.url,"metadata":{"topics":list(r.topics),"direction":r.direction,"matched_phrases":list(r.matched_phrases),"coverage_tags":list(r.sectors)}} for r in ordered]
    versions = taxonomy_versions()
    for entry in evidence:
        entry["metadata"]["taxonomy_versions"] = versions
    participant_names = sorted({r.canonical_agency_name for r in ordered if r.canonical_agency_name})
    coordination_name = participant_names[0] if len(participant_names) == 1 else f"{identity['coordination_agency_id']} ({'; '.join(participant_names)})"
    display_name = coordination_name or ordered[0].raw_agency
    return {**identity, "canonical_agency_name": display_name, "participating_agency_names":participant_names, "raw_agency_names": sorted({r.raw_agency for r in ordered}), "date_start": ordered[0].publication_date.isoformat(), "date_end": ordered[-1].publication_date.isoformat(), "label": f"{display_name} · {len(ordered)} actions · {dominant}", "direction": dominant, "matched_phrases": matched, "coverage_tags":[{"sector":a,"source":b,"matched_value":c} for a,b,c in coverage], "record_count":len(ordered), "document_type_counts":{t:sum(r.doc_type==t for r in ordered) for t in sorted({r.doc_type for r in ordered})}, "confidence":confidence, "confidence_reasons":["coherent exact metadata", f"direction coverage {direction_ratio:.0%}", "canonical agency known" if known else "agency unmapped", "all official URLs present" if urls else "missing official URL"], "priority_score":sum(components.values()), "priority_components":components, "evidence":evidence, "taxonomy_versions":versions, "lifecycle":"new"}

def detect_packages(conn: sqlite3.Connection, as_of: str, lookback_days: int = 14) -> list[dict[str, Any]]:
    end = date.fromisoformat(as_of); start = end - timedelta(days=lookback_days)
    rows = conn.execute("select * from records where source='fr' and publication_date between ? and ? order by publication_date,id", (start.isoformat(), end.isoformat())).fetchall()
    records = [enrich_record(r) for r in rows]
    def prior_for(component):
        ids = {r.record_id for r in component}; coordination = _coordination(component); start = min(r.publication_date for r in component); core_key = _core_key(component)
        candidates = conn.execute("select * from package_versions order by created_at desc").fetchall()
        ranked = []
        for prior in candidates:
            members = {x["record_id"] for x in conn.execute("select record_id from package_version_records where package_version_id=?", (prior["package_version_id"],))}
            if not members:
                try: members = {x["record_id"] for x in json.loads(prior["payload_json"]).get("evidence", [])}
                except (TypeError, json.JSONDecodeError): members = set()
            payload = json.loads(prior["payload_json"])
            overlap = len(ids & members)
            same_core = payload.get("core_cluster_key") == core_key
            same_coordination = payload.get("coordination_agency_id") == coordination["coordination_agency_id"]
            close_date = bool(payload.get("date_start") and abs((start - date.fromisoformat(payload["date_start"])).days) <= 2)
            if overlap or (same_core and same_coordination and close_date):
                ranked.append((overlap, int(same_core), -abs((start - date.fromisoformat(payload["date_start"])).days), payload.get("package_id", ""), payload))
        return max(ranked, key=lambda x: x[:-1])[-1] if ranked else None
    return [score_package(c, prior_state=prior_for(c)) for c in bounded_components(records, candidate_edges(records))]

def persist_package_versions(conn: sqlite3.Connection, packages: list[dict[str, Any]], now: str) -> list[dict[str, Any]]:
    out = []
    for package in sorted(packages, key=lambda p: p["package_id"]):
        member_ids = sorted(e["record_id"] for e in package.get("evidence", []))
        canonical = json.dumps({"package_id":package["package_id"],"records":member_ids,"direction":package["direction"],"confidence":package["confidence"],"taxonomy_versions":package.get("taxonomy_versions", taxonomy_versions())}, sort_keys=True, separators=(",", ":"))
        version_id = hashlib.sha256(canonical.encode()).hexdigest()[:16]
        prior = conn.execute("select * from package_versions where package_id=? order by created_at desc limit 1", (package["package_id"],)).fetchone()
        supersedes = prior["package_version_id"] if prior and prior["package_version_id"] != version_id else None
        if not prior or prior["package_version_id"] != version_id:
            conn.execute("insert or ignore into package_versions values (?, ?, ?, ?, ?, ?, ?)", (version_id, package["package_id"], supersedes, now, package["direction"], package["confidence"], json.dumps(package, sort_keys=True)))
            for record_id in member_ids:
                if conn.execute("select 1 from records where id=?", (record_id,)).fetchone():
                    conn.execute("insert or ignore into package_version_records values (?, ?)", (version_id, record_id))
        package = dict(package); package.update({"package_version_id":version_id,"supersedes_version_id":supersedes}); out.append(package)
    conn.commit(); return out
