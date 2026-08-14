"""Idempotent canonical agency normalization over records."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .taxonomy import AgencyIdentity, canonicalize_agency

def _raw(row: sqlite3.Row | dict[str, Any]) -> dict[str, Any]:
    value = row["raw_json"] if isinstance(row, sqlite3.Row) else row.get("raw_json")
    if isinstance(value, str):
        try: return json.loads(value)
        except json.JSONDecodeError: return {}
    return value or {}

def normalize_record_agency(conn: sqlite3.Connection, record_id: str) -> AgencyIdentity:
    row = conn.execute("select * from records where id = ?", (record_id,)).fetchone()
    if row is None: raise KeyError(record_id)
    identity = canonicalize_agency(row["source"], row["agency"] or "", _raw(row))
    from .taxonomy import AGENCY_CONFIG
    conn.execute("update records set canonical_agency_id=?, canonical_agency_name=?, agency_mapping_version=? where id=?",
                 (identity.canonical_id, identity.canonical_name, AGENCY_CONFIG["version"], record_id))
    if identity.canonical_id:
        conn.execute("""insert into agency_aliases(source, raw_name, canonical_id, canonical_name, parent_id, mapping_method)
                       values (?, ?, ?, ?, ?, ?) on conflict(source, raw_name) do update set
                       canonical_id=excluded.canonical_id, canonical_name=excluded.canonical_name,
                       parent_id=excluded.parent_id, mapping_method=excluded.mapping_method""",
                     (identity.source, identity.raw_name, identity.canonical_id, identity.canonical_name,
                      identity.parent_id, identity.mapping_method))
    return identity

def normalize_all(conn: sqlite3.Connection, batch_size: int = 5000) -> dict[str, int]:
    from .taxonomy import AGENCY_CONFIG
    version = AGENCY_CONFIG["version"]
    processed = 0
    last_id = ""
    size = max(1, batch_size)
    while True:
        rows = conn.execute("select id from records where id > ? and (agency_mapping_version is null or agency_mapping_version != ?) order by id limit ?", (last_id, version, size)).fetchall()
        if not rows:
            break
        for row in rows:
            normalize_record_agency(conn, row["id"])
            processed += 1
        last_id = rows[-1]["id"]
        conn.commit()
    mapped = conn.execute("select count(*) from records where canonical_agency_id is not null").fetchone()[0]
    unmapped = conn.execute("select count(*) from records where canonical_agency_id is null").fetchone()[0]
    return {"mapped": mapped, "unmapped": unmapped, "processed": processed, "mapping_version": version}
