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
the v2 pipeline, which records source failures explicitly while preserving the FR leg.
"""
from __future__ import annotations

import csv
import datetime as dt
import io
import json
import os
import re
import shutil
import sys
import tempfile
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


def _api_headers() -> dict[str, str]:
    # api.github.com is rate-limited to 60 req/hr per IP when unauthenticated;
    # CI runners share IPs, so ride the GITHUB_TOKEN Actions already provides.
    token = os.environ.get("GITHUB_TOKEN")
    return {**UA, "Authorization": f"Bearer {token}"} if token else dict(UA)


def _get_json(url: str) -> list[dict]:
    req = urllib.request.Request(url, headers=_api_headers())
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers=UA)
    fd, temporary = tempfile.mkstemp(prefix=f".{dest.name}.",suffix=".part",dir=dest.parent)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, os.fdopen(fd, "wb") as fh:
            shutil.copyfileobj(resp, fh); fh.flush(); os.fsync(fh.fileno())
        os.replace(temporary,dest)
    except Exception:
        try: os.close(fd)
        except OSError: pass
        try: os.unlink(temporary)
        except OSError: pass
        raise


def _safe_extract(archive: zipfile.ZipFile, destination: Path, *, max_files: int = 10_000, max_uncompressed_bytes: int = 2_000_000_000) -> None:
    destination=destination.resolve(); members=archive.infolist()
    if len(members) > max_files: raise ValueError(f"archive has too many members: {len(members)}")
    if sum(member.file_size for member in members) > max_uncompressed_bytes: raise ValueError("archive exceeds uncompressed size limit")
    for member in members:
        target=(destination/member.filename).resolve()
        if not target.is_relative_to(destination): raise ValueError(f"unsafe archive path: {member.filename}")
        if ((member.external_attr >> 16) & 0o170000) == 0o120000: raise ValueError(f"archive symlink rejected: {member.filename}")
    archive.extractall(destination)


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
        index = next((i for i, value in enumerate(normalized) if value in candidates), None)
        if index is None:
            raise ValueError(f"unrecognized deleted-record CSV header: {header!r}")
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


def sync(db_path: Path | str | None = None, conn=None, raw_dir: Path | None = None, marker_path: Path | None = None) -> int:
    raw_root = Path(raw_dir) if raw_dir else RAW
    marker = Path(marker_path) if marker_path else (raw_root / ".last_synced.json")
    raw_root.mkdir(parents=True, exist_ok=True)
    months = _available_months()
    if not months:
        print("marc_sync: no monthly files found")
        return 0
    if marker.exists():
        try: done = json.loads(marker.read_text())
        except (json.JSONDecodeError, OSError) as exc: raise ValueError(f"invalid MARC sync marker {marker}: {exc}") from exc
    else: done = {}
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
    owns_conn = conn is None
    if conn is None:
        from . import db
        conn = db.connect(db_path or ROOT / "data" / "fedpulse.db")
        db.init_db(conn)
    totals = {"new": 0, "changed": 0, "deleted": 0}

    try:
        entries_by_kind = {kind: _get_json(f"{API}/{folder}") for kind, folder in SETS.items()}
        for month in target:
            compact = month.replace("-", "")
            for kind, entries in entries_by_kind.items():
                for e in entries:
                    name = e.get("name", "")
                    if compact not in name:
                        continue
                    dest = raw_root / kind / month / name
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not dest.exists() or dest.stat().st_size != e.get("size"):
                        _download(e["download_url"], dest)
                    if kind == "deleted" and dest.suffix.lower() == ".csv":
                        totals["deleted"] += _delete_from_csv(conn, dest)["deleted"]
                        continue
                    if zipfile.is_zipfile(dest):
                        extract_dir = dest.with_suffix("")
                        with zipfile.ZipFile(dest) as z:
                            _safe_extract(z,extract_dir)
                        res = ingest._load_marc_dir(conn, extract_dir, kind)
                    else:
                        res = ingest._load_marc_dir(conn, dest.parent, kind)
                    totals[kind] += res.get("new", 0) + res.get("changed", 0) + res.get("deleted", 0)
        conn.commit()
        marker_tmp=marker.with_name(f".{marker.name}.tmp")
        marker_tmp.write_text(json.dumps({"month": latest, "at": dt.date.today().isoformat()}))
        os.replace(marker_tmp,marker)
    except Exception:
        conn.rollback()
        if owns_conn:
            conn.close()
        raise
    if owns_conn:
        conn.close()
    print(f"marc_sync: ingested through {latest} ({sum(totals.values())} ops)")
    return 0


if __name__ == "__main__":
    sys.exit(sync())
