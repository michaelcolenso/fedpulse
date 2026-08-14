"""SQLite storage layer. Stdlib only (sqlite3)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "schema.sql"
_BASE_COLUMNS = {
    "source": "TEXT", "title": "TEXT", "agency": "TEXT", "agency_slug": "TEXT",
    "sudoc": "TEXT", "sudoc_stem": "TEXT", "doc_type": "TEXT",
    "publication_date": "TEXT", "cataloged_date": "TEXT", "url": "TEXT",
    "subjects": "TEXT", "raw_json": "TEXT", "canonical_agency_id": "TEXT",
    "canonical_agency_name": "TEXT", "created_at": "TEXT",
    "updated_at": "TEXT",
}

def connect(db_path: str | Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def _ensure_column(conn: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
    names = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
    if column not in names:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

def init_db(conn: sqlite3.Connection) -> None:
    # A legacy records table may have only a subset of columns. Add the base
    # fields before schema indexes are created, then execute the full additive schema.
    existing = conn.execute("select name from sqlite_master where type='table' and name='records'").fetchone()
    if existing:
        for name, declaration in _BASE_COLUMNS.items():
            _ensure_column(conn, "records", name, declaration)
    conn.executescript(SCHEMA.read_text())
    conn.commit()

def upsert_record(conn: sqlite3.Connection, rec: dict) -> None:
    conn.execute(
        """INSERT INTO records
           (id, source, title, agency, agency_slug, sudoc, sudoc_stem, doc_type,
            publication_date, cataloged_date, url, subjects, raw_json,
            canonical_agency_id, canonical_agency_name)
           VALUES (:id, :source, :title, :agency, :agency_slug, :sudoc, :sudoc_stem, :doc_type,
                   :publication_date, :cataloged_date, :url, :subjects, :raw_json,
                   :canonical_agency_id, :canonical_agency_name)
           ON CONFLICT(id) DO UPDATE SET
             title=excluded.title, agency=excluded.agency, agency_slug=excluded.agency_slug,
             sudoc=excluded.sudoc, sudoc_stem=excluded.sudoc_stem, doc_type=excluded.doc_type,
             publication_date=excluded.publication_date, cataloged_date=excluded.cataloged_date,
             url=excluded.url, subjects=excluded.subjects, raw_json=excluded.raw_json,
             canonical_agency_id=COALESCE(excluded.canonical_agency_id, records.canonical_agency_id),
             canonical_agency_name=COALESCE(excluded.canonical_agency_name, records.canonical_agency_name),
             updated_at=datetime('now')""",
        {
            "id": rec["id"], "source": rec["source"], "title": rec.get("title"),
            "agency": rec.get("agency"), "agency_slug": rec.get("agency_slug"),
            "sudoc": rec.get("sudoc"), "sudoc_stem": rec.get("sudoc_stem"),
            "doc_type": rec.get("doc_type"), "publication_date": rec.get("publication_date"),
            "cataloged_date": rec.get("cataloged_date"), "url": rec.get("url"),
            "subjects": json.dumps(rec.get("subjects") or [], ensure_ascii=False),
            "raw_json": json.dumps(rec.get("raw_json") or {}, ensure_ascii=False)[:1_000_000],
            "canonical_agency_id": rec.get("canonical_agency_id"),
            "canonical_agency_name": rec.get("canonical_agency_name"),
        },
    )

def delete_record(conn: sqlite3.Connection, rec_id: str) -> None:
    conn.execute("DELETE FROM records WHERE id = ?", (rec_id,))

def note_subjects(conn: sqlite3.Connection, rec_id: str, cataloged_date: str, agency: str, subjects: list[str]) -> None:
    for subj in subjects:
        if not subj: continue
        conn.execute("""INSERT OR IGNORE INTO subject_first_seen
          (subject, first_seen_date, first_record_id, first_agency) VALUES (?, ?, ?, ?)""",
          (subj, cataloged_date or "", rec_id, agency or ""))

def start_run(conn: sqlite3.Connection, source: str) -> int:
    cur = conn.execute("INSERT INTO ingest_runs (source, started_at) VALUES (?, datetime('now'))", (source,))
    conn.commit(); return cur.lastrowid

def finish_run(conn: sqlite3.Connection, run_id: int, status: str, new=0, changed=0, deleted=0, notes=""):
    conn.execute("""UPDATE ingest_runs SET finished_at=datetime('now'), status=?, new_count=?, changed_count=?, deleted_count=?, notes=? WHERE run_id=?""",
                 (status, new, changed, deleted, notes[:500], run_id)); conn.commit()

def recent_runs(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM ingest_runs ORDER BY run_id DESC LIMIT ?", (limit,)).fetchall()
