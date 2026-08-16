"""Locked FedPulse pipeline entry point; tests inject fetch/sync functions and temp paths."""
from __future__ import annotations
import argparse
import datetime as dt
import fcntl
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Callable
from zoneinfo import ZoneInfo

from . import db, fr_client, marc_sync, regulations_client
from .health import record_attempt, record_failure, record_success
from .outputs_v2 import build_v2_outputs, publish_failure_outputs
from .regulatory_lifecycle import build_lifecycles, link_fr_documents, upsert_regulations_document

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

def pipeline_lock_path(db_path: Path) -> Path:
    db_path=Path(db_path)
    return db_path.with_name(f".{db_path.name}.pipeline.lock")

def run_pipeline(db_path: Path, out_dir: Path, as_of: str | None = None, *, ingest_fr: bool = True, sync_marc: bool = True, ingest_regulations: bool = True, fr_fetcher: Callable | None = None, marc_syncer: Callable | None = None, regulations_fetcher: Callable | None = None, regulations_api_key: str | None = None, now: dt.datetime | None = None) -> int:
    now = now or dt.datetime.now(dt.timezone.utc)
    if now.tzinfo is None: now = now.replace(tzinfo=dt.timezone.utc)
    as_of=as_of or now.astimezone(ZoneInfo("America/New_York")).date().isoformat(); out_dir=Path(out_dir)
    db_path=Path(db_path); lock_path=pipeline_lock_path(db_path)
    with acquire_lock(lock_path):
        conn=db.connect(db_path); db.init_db(conn); stamp=now.isoformat().replace("+00:00","Z"); record_attempt(conn,"pipeline",stamp)
        if ingest_fr:
            record_attempt(conn,"federal_register",stamp)
            try:
                docs=(fr_fetcher or fr_client.pull_days)()
                count=0
                conn.execute("begin immediate")
                for doc in docs:
                    row=doc if "source" in doc else fr_client.to_record(doc)
                    if not row.get("id") or row["id"] == "fr:" or (row.get("source") == "fr" and not row["id"].startswith("fr:")):
                        raise ValueError("Federal Register document is missing a valid document_number")
                    db.upsert_record(conn,row)
                    count += 1
                conn.commit(); record_success(conn,"federal_register",stamp,f"records={count}")
            except Exception as exc:
                conn.rollback(); record_failure(conn,"federal_register",stamp,str(exc)); record_failure(conn,"pipeline",stamp,str(exc))
                try: publish_failure_outputs(conn,as_of,out_dir,now,str(exc))
                finally: conn.close()
                return 1
        if sync_marc:
            record_attempt(conn,"marc",stamp)
            try:
                if marc_syncer is not None: marc_syncer()
                else: marc_sync.sync(db_path=db_path, raw_dir=out_dir / ".marc")
                record_success(conn,"marc",stamp,"maintenance sync complete")
            except Exception as exc:
                record_failure(conn,"marc",stamp,str(exc))
        if ingest_regulations:
            api_key = regulations_api_key or os.environ.get("REGULATIONS_GOV_API_KEY")
            if regulations_fetcher is not None or api_key:
                record_attempt(conn,"regulations_gov",stamp)
                try:
                    docs = regulations_fetcher() if regulations_fetcher is not None else regulations_client.pull_days(api_key, days=7)
                    conn.execute("begin immediate")
                    count = 0
                    for item in docs:
                        row = item if "document_id" in item else regulations_client.normalize_document(item)
                        if not row.get("document_id"):
                            raise ValueError("Regulations.gov document is missing document_id")
                        upsert_regulations_document(conn,row)
                        count += 1
                    links = link_fr_documents(conn)
                    lifecycles = build_lifecycles(conn,as_of)
                    conn.commit()
                    record_success(conn,"regulations_gov",stamp,f"documents={count}; links={links}; dockets={len(lifecycles)}")
                except Exception as exc:
                    conn.rollback(); record_failure(conn,"regulations_gov",stamp,str(exc))
            else:
                # Optional until the production api.data.gov key is configured.
                record_success(conn,"regulations_gov",stamp,"disabled: REGULATIONS_GOV_API_KEY not configured")
        record_success(conn,"pipeline",stamp,"sources complete; publishing v2 outputs")
        try:
            build_v2_outputs(conn,as_of,out_dir,now)
            conn.close(); return 0
        except Exception as exc:
            record_failure(conn,"pipeline",stamp,str(exc))
            try: publish_failure_outputs(conn,as_of,out_dir,now,str(exc))
            finally: conn.close()
            return 1

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(); parser.add_argument("--db",type=Path,default=Path("data/fedpulse.db")); parser.add_argument("--out",type=Path,default=Path("data/outputs")); parser.add_argument("--as-of"); parser.add_argument("--skip-ingest",action="store_true"); parser.add_argument("--skip-marc",action="store_true"); parser.add_argument("--skip-regulations",action="store_true"); args=parser.parse_args(argv)
    return run_pipeline(args.db,args.out,args.as_of,ingest_fr=not args.skip_ingest,sync_marc=not args.skip_marc,ingest_regulations=not args.skip_regulations)

if __name__=="__main__": raise SystemExit(main())
