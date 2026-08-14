from __future__ import annotations

import json
import sqlite3
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable

from fedpulse import db

FIXTURES = Path(__file__).parent / "fixtures" / "v2_records.json"

@contextmanager
def temp_db():
    with tempfile.TemporaryDirectory() as td:
        conn = db.connect(Path(td) / "test.sqlite")
        db.init_db(conn)
        try:
            yield conn
        finally:
            conn.close()

def load_case(name: str) -> list[dict[str, Any]]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))[name]

def seed_records(conn: sqlite3.Connection, rows: Iterable[dict[str, Any]]) -> int:
    rows = list(rows)
    for row in rows:
        db.upsert_record(conn, row)
    conn.commit()
    return len(rows)

def fr_record(record_id: str, agency: str, publication_date: str, *, title: str = "Fixture FR record", doc_type: str = "notice", topics: list[str] | None = None, action: str = "", abstract: str = "", url: str | None = None, agency_slug: str | None = None, agencies: list[dict] | None = None) -> dict[str, Any]:
    return {
        "id": record_id if record_id.startswith("fr:") else f"fr:{record_id}",
        "source": "fr", "title": title, "agency": agency, "agency_slug": agency_slug,
        "sudoc": None, "sudoc_stem": None, "doc_type": doc_type,
        "publication_date": publication_date, "cataloged_date": publication_date,
        "url": url or f"https://www.federalregister.gov/d/{record_id.replace(':', '-')}",
        "subjects": topics or [],
        "raw_json": {"action": action, "abstract": abstract, "agencies": agencies or []},
    }

def marc_record(record_id: str, agency: str, cataloged_date: str, *, title: str = "Fixture catalog record", subject: str = "Fixture subject", url: str | None = None) -> dict[str, Any]:
    return {
        "id": record_id if record_id.startswith("marc:") else f"marc:{record_id}",
        "source": "marc", "title": title, "agency": agency, "agency_slug": None,
        "sudoc": None, "sudoc_stem": None, "doc_type": "", "publication_date": None,
        "cataloged_date": cataloged_date, "url": url or f"https://catalog.gpo.gov/F/{record_id}",
        "subjects": [subject], "raw_json": {"subjects": [subject]},
    }
