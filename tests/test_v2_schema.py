import sqlite3
import tempfile
import unittest
from pathlib import Path

from fedpulse import db

class TestV2Schema(unittest.TestCase):
    def test_new_db_has_v2_tables_columns_indexes(self):
        with tempfile.TemporaryDirectory() as td:
            conn = db.connect(Path(td) / "new.sqlite")
            db.init_db(conn)
            cols = {r[1] for r in conn.execute("pragma table_info(records)")}
            self.assertTrue({"canonical_agency_id", "canonical_agency_name"} <= cols)
            tables = {r[0] for r in conn.execute("select name from sqlite_master where type='table'")}
            self.assertTrue({"agency_aliases", "signal_state", "package_versions", "package_version_records", "pipeline_state"} <= tables)
            indexes = {r[1] for r in conn.execute("pragma index_list(records)")}
            self.assertIn("idx_records_canonical_agency_date", indexes)
            self.assertIn("idx_package_versions_package", {r[1] for r in conn.execute("pragma index_list(package_versions)")})

    def test_init_twice_is_idempotent(self):
        with tempfile.TemporaryDirectory() as td:
            conn = db.connect(Path(td) / "twice.sqlite")
            db.init_db(conn)
            db.init_db(conn)
            self.assertEqual(conn.execute("select count(*) from records").fetchone()[0], 0)

    def test_legacy_records_are_preserved_and_migrated(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "legacy.sqlite"
            conn = sqlite3.connect(path)
            conn.execute("create table records (id text primary key, source text not null, agency text)")
            conn.execute("insert into records values ('fr:old','fr','Old Agency')")
            conn.commit(); conn.close()
            conn = db.connect(path)
            db.init_db(conn)
            row = conn.execute("select id, agency, canonical_agency_id from records").fetchone()
            self.assertEqual(tuple(row), ("fr:old", "Old Agency", None))

if __name__ == "__main__": unittest.main()
