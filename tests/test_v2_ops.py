import csv
import tempfile
import unittest
from pathlib import Path
from tests.v2_helpers import temp_db
from fedpulse import db
from fedpulse.health import record_attempt, record_failure, record_success, source_freshness
from fedpulse.marc_sync import _delete_from_csv

class TestOps(unittest.TestCase):
    def test_deleted_csv_header_variants_and_skips(self):
        for header in ("Sys. No.", "System Number", "System Number "):
            with tempfile.TemporaryDirectory() as td, temp_db() as conn:
                db.upsert_record(conn, {"id":"marc:123","source":"marc","agency":"A"})
                path=Path(td)/"deleted.csv"
                path.write_text(f"{header},Other\n123,x\nnot-a-number,x\n,x\n")
                result=_delete_from_csv(conn,path)
                self.assertEqual(result["valid_ids"],1,header)
                self.assertEqual(result["deleted"],1,header)
                self.assertEqual(result["skipped"],2,header)

    def test_health_state_and_staleness(self):
        with temp_db() as conn:
            record_attempt(conn,"federal_register","2026-08-10T00:00:00Z")
            record_success(conn,"federal_register","2026-08-10T00:01:00Z","ok")
            record_attempt(conn,"marc","2026-08-01T00:00:00Z")
            record_failure(conn,"marc","2026-08-01T00:01:00Z","timeout")
            fresh=source_freshness(conn,"2026-08-10T12:00:00Z")
            self.assertEqual(fresh["federal_register"]["status"],"fresh")
            self.assertEqual(fresh["marc"]["status"],"stale")
            self.assertEqual(fresh["marc"]["detail"],"timeout")

if __name__ == "__main__": unittest.main()
