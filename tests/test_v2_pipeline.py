import tempfile
import unittest
from pathlib import Path
from tests.v2_helpers import load_case, temp_db, seed_records
from fedpulse.pipeline_v2 import acquire_lock, run_pipeline

class TestPipeline(unittest.TestCase):
    def test_nonblocking_lock_prevents_overlap(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"lock"
            with acquire_lock(path):
                with self.assertRaises(RuntimeError):
                    with acquire_lock(path): pass

    def test_offline_quiet_run_generates_v2_brief(self):
        with tempfile.TemporaryDirectory() as td:
            db_path=Path(td)/"db.sqlite"; out=Path(td)/"outputs"
            from fedpulse import db
            conn=db.connect(db_path); db.init_db(conn); seed_records(conn,load_case("ncua_package")); conn.close()
            code=run_pipeline(db_path,out,"2026-08-06",ingest_fr=False,sync_marc=False)
            self.assertEqual(code,0); self.assertTrue((out/"brief.json").exists())

    def test_fr_failure_is_nonzero_without_production_paths(self):
        with tempfile.TemporaryDirectory() as td:
            code=run_pipeline(Path(td)/"db.sqlite",Path(td)/"out","2026-08-06",ingest_fr=True,sync_marc=False,fr_fetcher=lambda: (_ for _ in ()).throw(RuntimeError("offline")))
            self.assertNotEqual(code,0)

    def test_default_as_of_uses_eastern_calendar_and_marc_receives_custom_db(self):
        with tempfile.TemporaryDirectory() as td:
            from unittest.mock import patch
            import datetime as dt
            custom = Path(td) / "custom.sqlite"; out = Path(td) / "out"; seen = {}
            def sync(**kwargs): seen.update(kwargs)
            eastern_boundary = dt.datetime(2026, 8, 7, 1, 30, tzinfo=dt.timezone.utc)
            with patch("fedpulse.pipeline_v2.marc_sync.sync", side_effect=sync):
                code = run_pipeline(custom, out, as_of=None, now=eastern_boundary, ingest_fr=False, sync_marc=True)
            self.assertEqual(code, 0)
            self.assertEqual(seen["db_path"], custom)
            self.assertEqual(__import__("json").loads((out / "brief.json").read_text())["as_of"], "2026-08-06")

if __name__ == "__main__": unittest.main()
