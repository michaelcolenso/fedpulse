"""Locked v0.2 pipeline entry point; tests inject fetch/sync functions and temp paths."""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
from contextlib import contextmanager
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from . import db, fr_client, marc_sync
from .health import record_attempt, record_failure, record_success
from .outputs_v2 import build_v2_outputs

@contextmanager
def acquire_lock(path: Path):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); fh=path.open("a+")
    try:
        try: fcntl.flock(fh.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc: raise RuntimeError(f"FedPulse pipeline lock is already held: {path}") from exc
        yield fh
    finally:
        try: fcntl.flock(fh.fileno(),fcntl.LOCK_UN)
        finally: fh.close()

def run_pipeline(db_path: Path, out_dir: Path, as_of: str | None = None, *, ingest_fr: bool = True, sync_marc: bool = True, fr_fetcher: Callable | None = None, marc_syncer: Callable | None = None, now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None: now = now.replace(tzinfo=dt.timezone.utc)
    as_of=as_of or now.astimezone(ZoneInfo("America/New_York")).date().isoformat(); out_dir=Path(out_dir)
    with acquire_lock(out_dir/".pipeline.lock"):
        conn=db.connect(db_path); db.init_db(conn); stamp=now.isoformat().replace("+00:00","Z"); record_attempt(conn,"pipeline",stamp)
        if ingest_fr:
            record_attempt(conn,"federal_register",stamp)
            try:
                docs=(fr_fetcher or fr_client.pull_days)()
                for doc in docs:
                    row=doc if "source" in doc else fr_client.to_record(doc)
                    db.upsert_record(conn,row)
                conn.commit(); record_success(conn,"federal_register",stamp,f"records={len(docs)}")
            except Exception as exc:
                record_failure(conn,"federal_register",stamp,str(exc)); record_failure(conn,"pipeline",stamp,str(exc)); conn.close(); return 1
        if sync_marc:
            record_attempt(conn,"marc",stamp)
            try:
                if marc_syncer is not None: marc_syncer()
                else: marc_sync.sync(db_path=db_path, raw_dir=out_dir / ".marc")
                record_success(conn,"marc",stamp,"maintenance sync complete")
            except Exception as exc:
                record_failure(conn,"marc",stamp,str(exc))
        try:
            build_v2_outputs(conn,as_of,out_dir,now)
            record_success(conn,"pipeline",stamp,"v2 outputs written")
            conn.close(); return 0
        except Exception as exc:
            record_failure(conn,"pipeline",stamp,str(exc)); conn.close(); return 1

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--db",type=Path,default=Path("data/fedpulse.db")); parser.add_argument("--out",type=Path,default=Path("data/outputs")); parser.add_argument("--as-of"); parser.add_argument("--skip-ingest",action="store_true"); parser.add_argument("--skip-marc",action="store_true"); args=parser.parse_args(argv)
    return run_pipeline(args.db,args.out,args.as_of,ingest_fr=not args.skip_ingest,sync_marc=not args.skip_marc)

if __name__=="__main__": raise SystemExit(main())
