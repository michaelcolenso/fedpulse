import csv
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from tests.v2_helpers import temp_db
from fedpulse import db
from fedpulse.health import record_attempt, record_failure, record_success, source_freshness
from fedpulse.marc_sync import _delete_from_csv, _download, _safe_extract, sync

class TestOps(unittest.TestCase):
    def test_corrupt_marker_fails_loudly(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); marker=root/"marker.json"; marker.write_text("{broken")
            with patch("fedpulse.marc_sync._available_months",return_value=["2026-08"]), self.assertRaisesRegex(ValueError,"invalid MARC sync marker"):
                sync(db_path=root/"db.sqlite",raw_dir=root/"raw",marker_path=marker)

    def test_failed_download_preserves_existing_destination(self):
        class BrokenResponse:
            def __enter__(self): return self
            def __exit__(self,*_args): return False
            def read(self,_size=-1): raise OSError("connection reset")
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/"monthly.zip"; dest.write_bytes(b"known-good")
            with patch("fedpulse.marc_sync.urllib.request.urlopen",return_value=BrokenResponse()), self.assertRaises(OSError):
                _download("https://example.invalid/monthly.zip",dest)
            self.assertEqual(dest.read_bytes(),b"known-good")
            self.assertFalse(any(path.suffix == ".part" for path in Path(td).iterdir()))

    def test_zip_extraction_rejects_traversal_and_size_overflow(self):
        with tempfile.TemporaryDirectory() as td:
            for name,limit in (("../escape.mrc",100),("safe.mrc",2)):
                data=io.BytesIO()
                with zipfile.ZipFile(data,"w") as archive: archive.writestr(name,b"123")
                data.seek(0)
                with zipfile.ZipFile(data) as archive, self.assertRaises(ValueError):
                    _safe_extract(archive,Path(td)/"out",max_uncompressed_bytes=limit)

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

    def test_deleted_csv_unknown_header_fails_closed(self):
        with tempfile.TemporaryDirectory() as td, temp_db() as conn:
            db.upsert_record(conn, {"id":"marc:123","source":"marc","agency":"A"})
            conn.commit()
            path=Path(td)/"deleted.csv"
            path.write_text("OCLC,Other\n123,x\n")
            with self.assertRaises(ValueError):
                _delete_from_csv(conn,path)
            self.assertIsNotNone(conn.execute("select 1 from records where id='marc:123'").fetchone())

    def test_deletion_only_sync_commits_before_advancing_marker(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); db_path=root/"fedpulse.db"; raw=root/"raw"; marker=root/"marker.json"
            conn=db.connect(db_path); db.init_db(conn)
            db.upsert_record(conn, {"id":"marc:123","source":"marc","agency":"A"}); conn.commit(); conn.close()

            def entries(url):
                if "Deleted_Records_Lists" in url:
                    return [{"name":"202608_deleted_records.csv","size":13,"download_url":"https://example.invalid/deleted.csv"}]
                return []

            def download(_url, dest):
                dest.write_text("Sys. No.\n123\n")

            with patch("fedpulse.marc_sync._available_months", return_value=["2026-08"]), \
                 patch("fedpulse.marc_sync._get_json", side_effect=entries), \
                 patch("fedpulse.marc_sync._download", side_effect=download):
                self.assertEqual(sync(db_path=db_path, raw_dir=raw, marker_path=marker), 0)
            check=db.connect(db_path)
            self.assertIsNone(check.execute("select 1 from records where id='marc:123'").fetchone())
            check.close()
            self.assertEqual(__import__("json").loads(marker.read_text())["month"], "2026-08")

    def test_health_state_and_staleness(self):
        with temp_db() as conn:
            record_attempt(conn,"federal_register","2026-08-10T00:00:00Z")
            record_success(conn,"federal_register","2026-08-10T00:01:00Z","ok")
            record_attempt(conn,"marc","2026-08-01T00:00:00Z")
            record_failure(conn,"marc","2026-08-01T00:01:00Z","timeout")
            fresh=source_freshness(conn,"2026-08-10T12:00:00Z")
            self.assertEqual(fresh["federal_register"]["status"],"degraded")
            self.assertIn("no Federal Register records",fresh["federal_register"]["detail"])
            self.assertEqual(fresh["marc"]["status"],"stale")
            self.assertEqual(fresh["marc"]["detail"],"timeout")

    def test_health_exposes_schema_v2_source_dates(self):
        with temp_db() as conn:
            from tests.v2_helpers import fr_record, marc_record, seed_records
            seed_records(conn, [fr_record("fr-health", "Agency A", "2026-08-09"), marc_record("marc-health", "Agency A", "2026-08-08")])
            record_success(conn, "federal_register", "2026-08-10T00:00:00Z", "ok")
            record_success(conn, "marc", "2026-08-10T01:00:00Z", "maintenance")
            fresh=source_freshness(conn,"2026-08-10T12:00:00Z")
            self.assertEqual(fresh["federal_register"]["status"], "fresh")
            self.assertEqual(fresh["federal_register"]["last_publication_date"], "2026-08-09")
            self.assertEqual(fresh["federal_register"]["fetched_at"], "2026-08-10T00:00:00Z")
            self.assertEqual(fresh["marc"]["last_cataloged_date"], "2026-08-08")
            self.assertEqual(fresh["marc"]["maintenance_applied_at"], "2026-08-10T01:00:00Z")

if __name__ == "__main__": unittest.main()
