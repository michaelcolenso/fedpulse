import unittest
from tests.v2_helpers import load_case, temp_db, seed_records
from fedpulse.horizon import compute_marc_horizon, horizon_confidence

class TestHorizon(unittest.TestCase):
    def test_small_and_concentrated_batches_are_not_high(self):
        with temp_db() as conn:
            seed_records(conn, load_case("small_marc_batch") + load_case("concentrated_marc_batch"))
            result = compute_marc_horizon(conn, "2026-07-10")
            small = next(x for x in result["items"] if x["subject"] == "Small heading")
            concentrated = next(x for x in result["items"] if x["subject"] == "Batch heading")
            self.assertNotEqual(small["confidence"], "high")
            self.assertEqual(concentrated["confidence"], "catalog_batch_risk")

    def test_high_confidence_gates_and_cataloged_wording(self):
        rows=[]
        for i in range(10):
            rows.append({"id":f"marc:h-{i}","source":"marc","title":"High","agency":["National Credit Union Administration","Centers for Disease Control and Prevention","National Institute of Standards and Technology"][i%3],"doc_type":"","publication_date":None,"cataloged_date":f"2026-07-{1+i%5:02d}","url":f"https://catalog.gpo.gov/F/h-{i}","subjects":["Emerging heading"],"raw_json":{}})
        item = horizon_confidence(rows)
        self.assertEqual(item["confidence"], "high")
        self.assertIn("cataloged", item["first_seen_label"].lower())
        self.assertEqual(len(item["evidence"]), 10)

    def test_federal_register_rows_never_enter_horizon(self):
        with temp_db() as conn:
            seed_records(conn, [{"id":"fr:x","source":"fr","title":"x","agency":"A","doc_type":"notice","publication_date":"2026-07-01","cataloged_date":"2026-07-01","url":"https://www.federalregister.gov/d/x","subjects":["Emerging heading"],"raw_json":{}}])
            self.assertEqual(compute_marc_horizon(conn, "2026-07-10")["items"], [])

if __name__ == "__main__": unittest.main()
