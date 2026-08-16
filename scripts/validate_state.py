#!/usr/bin/env python3
"""Fail closed when a restored or newly generated FedPulse SQLite DB is unsafe to persist."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

REQUIRED_TABLES = {"records", "signal_state", "package_versions", "source_health"}


def inspect(path: Path) -> dict[str, object]:
    if not path.is_file() or path.stat().st_size == 0:
        raise SystemExit(f"state database is missing or empty: {path}")
    conn = sqlite3.connect(path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            raise SystemExit(f"SQLite integrity_check failed: {integrity}")
        tables = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            raise SystemExit(f"state database missing required tables: {sorted(missing)}")
        records = int(conn.execute("select count(*) from records").fetchone()[0])
        fr = int(conn.execute("select count(*) from records where source='fr'").fetchone()[0])
        marc = int(conn.execute("select count(*) from records where source='marc'").fetchone()[0])
        return {"records": records, "fr_records": fr, "marc_records": marc, "bytes": path.stat().st_size}
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("db", type=Path)
    parser.add_argument("--baseline-json", type=Path)
    parser.add_argument("--write-json", type=Path)
    parser.add_argument("--max-shrink-fraction", type=float, default=0.10)
    args = parser.parse_args()

    stats = inspect(args.db)
    if args.baseline_json and args.baseline_json.exists():
        baseline = json.loads(args.baseline_json.read_text())
        old = int(baseline.get("records", 0))
        new = int(stats["records"])
        if old > 0 and new < old * (1 - args.max_shrink_fraction):
            raise SystemExit(f"refusing suspicious state shrink: {old} -> {new} records")

    if args.write_json:
        args.write_json.parent.mkdir(parents=True, exist_ok=True)
        args.write_json.write_text(json.dumps(stats, sort_keys=True) + "\n")
    print(json.dumps(stats, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
