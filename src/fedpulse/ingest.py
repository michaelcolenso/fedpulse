"""Ingest orchestration: FR daily pull + MARC delta load → SQLite upserts.

Usage:
  python -m fedpulse.ingest fr --days 3
  python -m fedpulse.ingest fr --backfill 2021-01-01
  python -m fedpulse.ingest marc --dir data/raw/monthly  (New/Changed/Deleted subdirs)
  python -m fedpulse.ingest marc --dir data/raw/all       (full-catalog MARCXML zips)
  python -m fedpulse.ingest all
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from . import db, fr_client, marc_parser

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "fedpulse.db"


def get_conn() -> db.sqlite3.Connection:
    conn = db.connect(DB_PATH)
    db.init_db(conn)
    return conn


def ingest_fr(conn, days: int | None = None, backfill_start: str | None = None) -> dict:
    run_id = db.start_run(conn, "fr")
    docs: list[dict] = []
    if backfill_start:
        print(f"Backfilling FR from {backfill_start} ...")
        docs = fr_client.backfill(backfill_start)
    else:
        docs = fr_client.pull_days(days or 3)
    new = changed = 0
    for doc in docs:
        rec = fr_client.to_record(doc)
        if not rec["id"].endswith(":"):
            continue
        cur = conn.execute("SELECT id FROM records WHERE id = ?", (rec["id"],)).fetchone()
        db.upsert_record(conn, rec)
        if cur:
            changed += 1
        else:
            new += 1
            db.note_subjects(conn, rec["id"], rec["cataloged_date"] or "", rec["agency"] or "", rec["subjects"])
    conn.commit()
    db.finish_run(conn, run_id, "ok", new=new, changed=changed, notes=f"{len(docs)} docs")
    print(f"FR ingest: {new} new, {changed} changed, {len(docs)} total")
    return {"new": new, "changed": changed, "total": len(docs)}


def _load_marc_dir(conn, directory: Path, kind: str) -> dict:
    """kind: 'new' | 'changed' | 'deleted' | 'all'."""
    run_id = db.start_run(conn, f"marc:{kind}")
    new = changed = deleted = 0
    files = sorted(directory.rglob("*"))
    marc_files = [f for f in files if f.suffix.lower() in (".xml", ".mrc", ".utf8", ".txt") and "readme" not in f.name.lower()]
    for i, f in enumerate(marc_files, 1):
        raw = f.read_bytes()
        try:
            if f.suffix.lower() == ".xml":
                parsed = marc_parser.parse_marcxml(raw)
            else:
                parsed = marc_parser.parse_marc_binary(raw)
        except Exception as e:  # malformed record — skip, log
            print(f"  parse error {f.name}: {e}")
            continue
        for rec in parsed:
            norm = marc_parser.normalize_record(rec)
            if not norm:
                continue
            if kind == "deleted":
                db.delete_record(conn, norm["id"])
                deleted += 1
                continue
            cur = conn.execute("SELECT id FROM records WHERE id = ?", (norm["id"],)).fetchone()
            db.upsert_record(conn, norm)
            if cur:
                changed += 1
            else:
                new += 1
            if kind in ("new", "all"):
                db.note_subjects(conn, norm["id"], norm["cataloged_date"] or "", norm["agency"] or "", norm["subjects"])
        if i % 200 == 0:
            conn.commit()
    conn.commit()
    db.finish_run(conn, run_id, "ok", new=new, changed=changed, deleted=deleted, notes=f"{len(marc_files)} files")
    print(f"MARC {kind}: {new} new, {changed} changed, {deleted} deleted, {len(marc_files)} files")
    return {"new": new, "changed": changed, "deleted": deleted, "files": len(marc_files)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="fedpulse-ingest")
    ap.add_argument("target", choices=["fr", "marc", "all"])
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--backfill", type=str, default=None, help="ISO date, e.g. 2021-01-01")
    ap.add_argument("--dir", type=Path, default=None, help="MARC directory (raw/… or raw/all)")
    args = ap.parse_args(argv)

    conn = get_conn()
    try:
        if args.target in ("fr", "all"):
            ingest_fr(conn, days=args.days, backfill_start=args.backfill)
        if args.target in ("marc", "all"):
            d = args.dir or (Path(__file__).resolve().parents[2] / "data" / "raw" / "monthly")
            if not d.exists():
                print(f"MARC dir {d} does not exist — skipping (run download step first).", file=sys.stderr)
            else:
                for sub in ("new", "changed", "deleted"):
                    subdir = d / sub
                    if subdir.exists():
                        _load_marc_dir(conn, subdir, sub)
        conn.close()
        return 0
    except Exception as e:
        print(f"FATAL: {e}", file=sys.stderr)
        conn.close()
        return 1


if __name__ == "__main__":
    sys.exit(main())
