"""MARC monthly delta sync — pulls the newest monthly New/Changed/Deleted files
from GPO's maintenance repo when a new month lands.

GPO pushes monthly files to:
  https://github.com/usgpo/cataloging-records-CGP-maintenance-files
  → CGP_Records_Monthly_Files/{New_MARC_Records,Changed_MARC_Records,Deleted_Records_Lists}/…

Naming convention (per GPO README): <YYYY-MM>_<set>.zip-ish — exact names are
resolved at runtime from the GitHub API, so this survives GPO renaming.

Design: list remote dir, take the newest filename per set, skip if we've already
ingested that month (marker file), download to data/raw/monthly/, ingest.

Network-dependent: called from nightly.sh with `|| true` so a blocked/absent
network never breaks the FR leg.
"""
from __future__ import annotations

import json
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


def _get_json(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def latest_month() -> str | None:
    """Return the newest '<YYYY-MM>' appearing across the monthly subdirs, or None."""
    months: set[str] = set()
    for folder in SETS.values():
        try:
            entries = _get_json(f"{API}/{folder}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        for e in entries:
            name = e.get("name", "")
            if len(name) >= 7 and name[4] == "-" and name[:7][:4].isdigit():
                months.add(name[:7])
    return max(months) if months else None


def sync() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    month = latest_month()
    if not month:
        print("marc_sync: no monthly files found")
        return 0
    try:
        done = json.loads(MARKER.read_text()) if MARKER.exists() else {}
    except (json.JSONDecodeError, OSError):
        done = {}
    if done.get("month") == month:
        return 0  # already ingested this month

    print(f"marc_sync: new month {month} — downloading delta")
    files: list[tuple[str, Path]] = []
    for kind, folder in SETS.items():
        entries = _get_json(f"{API}/{folder}")
        for e in entries:
            if e.get("name", "").startswith(month):
                dest = RAW / kind / e["name"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                _download(e["download_url"], dest)
                files.append((kind, dest))

    # Ingest (delegates to ingest.py's loader) then mark the month done.
    from . import db, ingest
    conn = db.connect(ROOT / "data" / "fedpulse.db")
    db.init_db(conn)
    counts = {"new": 0, "changed": 0, "deleted": 0}
    for kind, path in files:
        if zipfile.is_zipfile(path):
            extract_dir = path.with_suffix("")
            with zipfile.ZipFile(path) as z:
                z.extractall(extract_dir)
            res = ingest._load_marc_dir(conn, extract_dir, kind)
        else:
            res = ingest._load_marc_dir(conn, path.parent, kind)
        counts[kind] += res.get("new", 0) + res.get("changed", 0) + res.get("deleted", 0)
    conn.close()
    MARKER.write_text(json.dumps({"month": month, "at": __import__("datetime").date.today().isoformat()}))
    print(f"marc_sync: ingested {month} ({sum(counts.values())} ops)")
    return 0


if __name__ == "__main__":
    sys.exit(sync())
