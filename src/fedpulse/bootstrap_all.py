"""Full-catalog bootstrap — download all 28 GPO MARC UTF-8 record-set zips
(Git LFS media endpoint, no git-lfs client needed), unzip, ingest.

Source: https://github.com/usgpo/cataloging-records-all-cgp-utf8
(~1.1M records total; complete CGP snapshot, refreshed periodically by GPO).

Resume-friendly: skips zips already downloaded at the right size; marker file
records completion. Run once for history, then the monthly sync keeps it fresh.
"""
from __future__ import annotations

import datetime as dt
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "all-cgp"
UNPACK = RAW / "unpacked"
MARKER = RAW / ".last_bootstrap.json"
BASE_URL = "https://media.githubusercontent.com/media/usgpo/cataloging-records-all-cgp-utf8/main/Record_sets"
UA = {"User-Agent": "FedPulse/0.1 (regulatory metadata index)"}
N_FILES = 28


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=600) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def bootstrap() -> int:
    RAW.mkdir(parents=True, exist_ok=True)
    UNPACK.mkdir(parents=True, exist_ok=True)
    try:
        done = json.loads(MARKER.read_text()) if MARKER.exists() else {}
    except (json.JSONDecodeError, OSError):
        done = {}
    if done.get("complete"):
        print("bootstrap_all: already complete; nothing to do")
        return 0

    from . import db, ingest
    conn = db.connect(ROOT / "data" / "fedpulse.db")
    db.init_db(conn)

    total_new = total_changed = 0
    for i in range(1, N_FILES + 1):
        fname = f"cataloging-records-all-cgp-utf8-{i:02d}.mrc.zip"
        dest = RAW / fname
        if not dest.exists() or dest.stat().st_size < 1_000_000:
            print(f"bootstrap_all: downloading {fname} ({i}/{N_FILES})")
            _download(f"{BASE_URL}/{fname}", dest)
        out_dir = UNPACK / f"set-{i:02d}"
        if not out_dir.exists():
            out_dir.mkdir(parents=True)
            with zipfile.ZipFile(dest) as z:
                z.extractall(out_dir)
        res = ingest._load_marc_dir(conn, out_dir, "all")
        total_new += res.get("new", 0)
        total_changed += res.get("changed", 0)
        print(f"bootstrap_all: set {i:02d} → {res.get('new',0)} new / {res.get('changed',0)} changed")
    conn.close()
    MARKER.write_text(json.dumps({"complete": True, "at": dt.date.today().isoformat(),
                                  "new": total_new, "changed": total_changed}))
    print(f"bootstrap_all: DONE — {total_new} new, {total_changed} changed")
    return 0


if __name__ == "__main__":
    sys.exit(bootstrap())
