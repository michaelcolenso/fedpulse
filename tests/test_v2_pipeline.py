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

if __name__ == "__main__": unittest.main()
