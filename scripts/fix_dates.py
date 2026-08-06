"""One-off data migration: recompute cataloged_dates with the fixed 2-digit-year
window, then rebuild subject_first_seen from the true MIN(cataloged_date) per
subject. Run once after the date-parser fix; safe to re-run.

Why: the naive 'YY>=90 → 19xx' rule misdated ~294k records cataloged 1965-1989
as 2065-2089, which poisoned TER emergence (everything looked 'new').
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from fedpulse import marc_parser  # noqa: E402

DB = Path(__file__).resolve().parents[1] / "data" / "fedpulse.db"


def fix_dates(conn: sqlite3.Connection) -> int:
    rows = conn.execute("SELECT id, raw_json FROM records WHERE source='marc'").fetchall()
    print(f"recomputing dates for {len(rows)} marc records ...", flush=True)
    updates = []
    for i, (rid, raw) in enumerate(rows):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        norm = marc_parser.normalize_record(parsed)
        if norm and norm.get("cataloged_date"):
            updates.append((norm["cataloged_date"], rid))
        if i % 100_000 == 0 and i:
            print(f"  {i} ...", flush=True)
    conn.executemany("UPDATE records SET cataloged_date=? WHERE id=?", updates)
    conn.commit()
    print(f"updated {len(updates)} cataloged_dates")
    return len(updates)


def rebuild_first_seen(conn: sqlite3.Connection) -> int:
    conn.execute("DELETE FROM subject_first_seen")
    conn.execute(
        """INSERT INTO subject_first_seen (subject, first_seen_date, first_record_id, first_agency)
           SELECT subject, min_date, record_id, agency FROM (
             SELECT s.value AS subject,
                    COALESCE(r.cataloged_date, r.publication_date, '') AS min_date,
                    r.id AS record_id, r.agency AS agency,
                    ROW_NUMBER() OVER (
                      PARTITION BY s.value
                      ORDER BY COALESCE(r.cataloged_date, r.publication_date, ''), r.id
                    ) AS rn
             FROM records r, json_each(r.subjects) AS s
             WHERE r.subjects != '[]' AND r.subjects IS NOT NULL
           ) WHERE rn = 1"""
    )
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM subject_first_seen").fetchone()[0]
    print(f"rebuilt subject_first_seen: {n} subjects")
    return n


def main() -> int:
    conn = sqlite3.connect(DB, timeout=60)
    conn.execute("PRAGMA busy_timeout = 60000")
    try:
        fix_dates(conn)
        rebuild_first_seen(conn)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
