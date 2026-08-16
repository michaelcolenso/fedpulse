import datetime as dt
import tempfile
import unittest
from pathlib import Path

from fedpulse import db, sam_opportunities_client
from fedpulse.action_graph import upsert_events
from fedpulse.opportunities import rank_opportunities


class SamGeographyTests(unittest.TestCase):
    def _rank(self, csv_text: str):
        events = sam_opportunities_client.parse_csv(csv_text.encode("utf-8"))
        root = Path(tempfile.mkdtemp())
        conn = db.connect(root / "test.db")
        db.init_db(conn)
        upsert_events(conn, events)
        conn.commit()
        return events, rank_opportunities(conn, "2026-08-16", "pnw_intelligence", 20)

    def test_contracting_office_city_is_not_project_geography(self):
        body = "\n".join([
            "NoticeId,Title,Department/Ind.Agency,PostedDate,Type,City,State,PopCity,PopState,NaicsCode,ResponseDeadLine,Link",
            "foreign-1,Embassy window replacement,STATE DEPARTMENT,2026-08-14,Presolicitation,Washington,DC,Kigali,,238150,2026-08-25,https://sam.gov/foreign-1",
        ])
        events, ranked = self._rank(body)
        stored_row = events[0].payload["row"]
        self.assertNotIn("City", stored_row)
        self.assertNotIn("State", stored_row)
        self.assertEqual(stored_row["PopCity"], "Kigali")
        self.assertFalse(any(item["event_id"] == "sam_opportunity:foreign-1" for item in ranked))

    def test_place_of_performance_can_match_pnw(self):
        body = "\n".join([
            "NoticeId,Title,Department/Ind.Agency,PostedDate,Type,City,State,PopCity,PopState,NaicsCode,ResponseDeadLine,Link",
            "wa-1,Federal facility roof repair,GENERAL SERVICES ADMINISTRATION,2026-08-14,Sources Sought,Washington,DC,Tacoma,Washington,238160,2026-08-25,https://sam.gov/wa-1",
        ])
        events, ranked = self._rank(body)
        stored_row = events[0].payload["row"]
        self.assertEqual(stored_row["PopCity"], "Tacoma")
        self.assertEqual(stored_row["PopState"], "Washington")
        match = next(item for item in ranked if item["event_id"] == "sam_opportunity:wa-1")
        self.assertTrue(any(reason.startswith("geography:") for reason in match["reasons"]))


if __name__ == "__main__":
    unittest.main()
