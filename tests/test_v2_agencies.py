import unittest
from tests.v2_helpers import load_case, temp_db, seed_records
from fedpulse import db
from fedpulse.normalize_agencies import normalize_all, normalize_record_agency
from fedpulse.fr_client import to_record

class TestAgencies(unittest.TestCase):
    def test_normalize_preserves_raw_and_canonicalizes_cdc_variants(self):
        rows = load_case("cdc_funding_package")[:2]
        with temp_db() as conn:
            seed_records(conn, rows)
            result = normalize_all(conn)
            self.assertEqual(result["mapped"], 2)
            got = conn.execute("select agency, canonical_agency_id, canonical_agency_name from records order by id").fetchall()
            self.assertEqual({r[0] for r in got}, {"Centers for Disease Control and Prevention", "Centers for Disease Control and Prevention (U.S.)"})
            self.assertEqual({r[1] for r in got}, {"cdc"})
            self.assertEqual(conn.execute("select count(*) from agency_aliases").fetchone()[0], 2)

    def test_unmapped_is_explicit_null_and_idempotent(self):
        row = load_case("small_marc_batch")[0]
        with temp_db() as conn:
            seed_records(conn, [row])
            self.assertIsNone(normalize_record_agency(conn, row["id"]).canonical_id)
            first = normalize_all(conn); second = normalize_all(conn)
            self.assertEqual(first, second)
            self.assertIsNone(conn.execute("select canonical_agency_id from records").fetchone()[0])

    def test_fr_mapping_keeps_full_agency_provenance(self):
        doc = {"document_number":"X-1","type":"Rule","title":"x","publication_date":"2026-01-01","html_url":"https://www.federalregister.gov/d/x","agencies":[{"id":999,"name":"Centers for Disease Control and Prevention","slug":"cdc","parent_id":100}],"topics":[],"action":"","abstract":""}
        row = to_record(doc)
        self.assertEqual(row["agency"], "Centers for Disease Control and Prevention")
        self.assertEqual(row["raw_json"]["agencies"][0]["parent_id"], 100)
        self.assertEqual(row["canonical_agency_id"], "cdc")

if __name__ == "__main__": unittest.main()
