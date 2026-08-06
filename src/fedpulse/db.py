"""SQLite storage layer. Stdlib only (sqlite3)."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

SCHEMA = Path(__file__).parent / "schema.sql"

def connect(db_path: str | Path) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn

def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text())
    conn.commit()

def upsert_record(conn: sqlite3.Connection, rec: dict) -> None:
    """Insert or update a single record. rec keys match the records table."""
    conn.execute(
        """INSERT INTO records
           (id, source, title, agency, agency_slug, sudoc, sudoc_stem, doc_type,
            publication_date, cataloged_date, url, subjects, raw_json)
           VALUES (:id, :source, :title, :agency, :agency_slug, :sudoc, :sudoc_stem, :doc_type,
                   :publication_date, :cataloged_date, :url, :subjects, :raw_json)
           ON CONFLICT(id) DO UPDATE SET
             title=excluded.title, agency=excluded.agency, agency_slug=excluded.agency_slug,
             sudoc=excluded.sudoc, sudoc_stem=excluded.sudoc_stem, doc_type=excluded.doc_type,
             publication_date=excluded.publication_date, cataloged_date=excluded.cataloged_date,
             url=excluded.url, subjects=excluded.subjects, raw_json=excluded.raw_json,
             updated_at=datetime('now')""",
        {
            "id": rec["id"],
            "source": rec["source"],
            "title": rec.get("title"),
            "agency": rec.get("agency"),
            "agency_slug": rec.get("agency_slug"),
            "sudoc": rec.get("sudoc"),
            "sudoc_stem": rec.get("sudoc_stem"),
            "doc_type": rec.get("doc_type"),
            "publication_date": rec.get("publication_date"),
            "cataloged_date": rec.get("cataloged_date"),
            "url": rec.get("url"),
            "subjects": json.dumps(rec.get("subjects") or [], ensure_ascii=False),
            "raw_json": json.dumps(rec.get("raw_json") or {}, ensure_ascii=False)[:1_000_000],
        },
    )

def delete_record(conn: sqlite3.Connection, rec_id: str) -> None:
    conn.execute("DELETE FROM records WHERE id = ?", (rec_id,))

def note_subjects(conn: sqlite3.Connection, rec_id: str, cataloged_date: str, agency: str, subjects: list[str]) -> None:
    """Record first-seen dates for subject headings (TER emergence input)."""
    for subj in subjects:
        if not subj:
            continue
        conn.execute(
            """INSERT OR IGNORE INTO subject_first_seen (subject, first_seen_date, first_record_id, first_agency)
               VALUES (?, ?, ?, ?)""",
            (subj, cataloged_date or "", rec_id, agency or ""),
        )

def start_run(conn: sqlite3.Connection, source: str) -> int:
    cur = conn.execute(
        "INSERT INTO ingest_runs (source, started_at) VALUES (?, datetime('now'))",
        (source,),
    )
    conn.commit()
    return cur.lastrowid

def finish_run(conn: sqlite3.Connection, run_id: int, status: str, new=0, changed=0, deleted=0, notes=""):
    conn.execute(
        """UPDATE ingest_runs SET finished_at=datetime('now'), status=?, new_count=?, changed_count=?, deleted_count=?, notes=?
           WHERE run_id=?""",
        (status, new, changed, deleted, notes[:500], run_id),
    )
    conn.commit()

def recent_runs(conn: sqlite3.Connection, limit: int = 10) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM ingest_runs ORDER BY run_id DESC LIMIT ?", (limit,)
    ).fetchall()
