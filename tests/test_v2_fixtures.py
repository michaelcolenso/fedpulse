import json
import unittest
from pathlib import Path

REQUIRED_CASES = {
    "ncua_package", "phmsa_package", "cdc_funding_package", "nist_standalone",
    "unrelated_same_day_notices", "transitive_date_chain", "negated_direction",
    "zero_variance_weeks", "small_marc_batch", "concentrated_marc_batch",
}

class TestV2Fixtures(unittest.TestCase):
    def test_fixture_contract_has_all_cases_and_metadata(self):
        path = Path(__file__).parent / "fixtures" / "v2_records.json"
        data = json.loads(path.read_text())
        self.assertTrue(REQUIRED_CASES <= set(data))
        for case, rows in data.items():
            self.assertIsInstance(rows, list, case)
            self.assertTrue(rows, case)
            for row in rows:
                for key in ("id", "source", "title", "agency", "doc_type", "url", "raw_json"):
                    self.assertIn(key, row, f"{case}: {key}")
                if row["source"] == "fr":
                    self.assertRegex(row["url"], r"^https://www\.federalregister\.gov/")
                    self.assertTrue(row.get("publication_date"))
                else:
                    self.assertTrue(row.get("cataloged_date"))

    def test_helpers_load_and_seed_contract(self):
        from tests.v2_helpers import load_case, marc_record, fr_record, seed_records, temp_db
        rows = load_case("nist_standalone")
        self.assertEqual(len(rows), 1)
        with temp_db() as conn:
            self.assertEqual(seed_records(conn, rows), 1)
            self.assertEqual(conn.execute("select count(*) from records").fetchone()[0], 1)
        self.assertEqual(fr_record("x", "A", "2026-01-01")["source"], "fr")
        self.assertEqual(marc_record("x", "A", "2026-01-01")["source"], "marc")

if __name__ == "__main__":
    unittest.main()
