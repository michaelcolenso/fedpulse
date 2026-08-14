"""MARC monthly delta sync — pulls the newest monthly New/Changed/Deleted files
from GPO's maintenance repo when a new month lands.

GPO pushes monthly files to:
  https://github.com/usgpo/cataloging-records-CGP-maintenance-files
  → CGP_Records_Monthly_Files/
      New_MARC_Records/     new_records_YYYYMM_<n>_utf8.mrc
      Changed_MARC_Records/ changed_records_YYYYMM_<n>_utf8.mrc
      Deleted_Records_Lists/ YYYYMM_deleted_records.csv   (System Number,OCLC)

Design: list remote dir, take the newest month across all sets, skip if already
ingested (marker file), download, ingest. Network-dependent — called from
nightly.sh with `|| true` so a blocked network never breaks the FR leg.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import re
import shutil
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "monthly"
MARKER = ROOT / "data" / "raw" / "monthly" / ".last_synced.json"
API = "https://api.github.com/repos/usgpo/cataloging-records-CGP-maintenance-files/contents/CGP_Records_Monthly_Files"
UA = {"User-Agent": "FedPulse/0.1 (regulatory metadata index)"}

SETS = {
    "new": "New_MARC_Records",
    "changed": "Changed_MARC_Records",
    "deleted": "Deleted_Records_Lists",
}

MONTH_RE = re.compile(r"(\d{4})(\d{2})")


def _get_json(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def _delete_from_csv(conn, path: Path) -> dict:
    """Delete records from observed GPO CSV header variants with audit counts."""
    from . import db
    rows = valid_ids = deleted = not_present = skipped = 0
    header_name = ""
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.reader(fh)
        try: header = next(reader)
        except StopIteration: return {"rows":0,"valid_ids":0,"deleted":0,"not_present":0,"skipped":0,"header":""}
        normalized = [re.sub(r"[^a-z0-9]", "", h.casefold()) for h in header]
        candidates = {"sysno", "systemnumber"}
        index = next((i for i, value in enumerate(normalized) if value in candidates), 0)
        header_name = header[index].strip() if header else ""
        for values in reader:
            rows += 1
            value = values[index].strip() if index < len(values) else ""
            if not value or not value.isdigit(): skipped += 1; continue
            valid_ids += 1
            cur = conn.execute("select 1 from records where id=?", (f"marc:{value}",)).fetchone()
            if cur: db.delete_record(conn, f"marc:{value}"); deleted += 1
            else: not_present += 1
    return {"rows":rows,"valid_ids":valid_ids,"deleted":deleted,"not_present":not_present,"skipped":skipped,"header":header_name}


def _available_months() -> list[str]:
    months: set[str] = set()
    for folder in SETS.values():
        try:
            entries = _get_json(f"{API}/{folder}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        for e in entries:
            m = MONTH_RE.search(e.get("name", ""))
            if not m:
                continue
            y, mo = int(m.group(1)), int(m.group(2))
            if 1990 <= y <= 2100 and 1 <= mo <= 12:
                months.add(f"{y:04d}-{mo:02d}")
    return sorted(months)


def sync() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    months = _available_months()
    if not months:
        print("marc_sync: no monthly files found")
        return 0
    try:
        done = json.loads(MARKER.read_text()) if MARKER.exists() else {}
    except (json.JSONDecodeError, OSError):
        done = {}
    done_month = done.get("month")
    latest = months[-1]
    if done_month == latest:
        return 0  # already current
    if done_month:
        target = [m for m in months if m > done_month]
    else:
        target = months  # first run: ingest everything available
    print(f"marc_sync: ingesting {target[0]}..{target[-1]} ({len(target)} months)")

    from . import db, ingest
    conn = db.connect(ROOT / "data" / "fedpulse.db")
    db.init_db(conn)
    totals = {"new": 0, "changed": 0, "deleted": 0}

    for month in target:
        compact = month.replace("-", "")
        for kind, folder in SETS.items():
            entries = _get_json(f"{API}/{folder}")
            for e in entries:
                name = e.get("name", "")
                if compact not in name:
                    continue
                dest = RAW / kind / month / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                if not dest.exists() or dest.stat().st_size != e.get("size"):
                    _download(e["download_url"], dest)
                if kind == "deleted" and dest.suffix.lower() == ".csv":
                    totals["deleted"] += _delete_from_csv(conn, dest)["deleted"]
                    continue
                if zipfile.is_zipfile(dest):
                    extract_dir = dest.with_suffix("")
                    with zipfile.ZipFile(dest) as z:
                        z.extractall(extract_dir)
                    res = ingest._load_marc_dir(conn, extract_dir, kind)
                else:
                    res = ingest._load_marc_dir(conn, dest.parent, kind)
                totals[kind] += res.get("new", 0) + res.get("changed", 0) + res.get("deleted", 0)
    conn.close()
    MARKER.write_text(json.dumps({"month": latest, "at": dt.date.today().isoformat()}))
    print(f"marc_sync: ingested through {latest} ({sum(totals.values())} ops)")
    return 0


if __name__ == "__main__":
    sys.exit(sync())
