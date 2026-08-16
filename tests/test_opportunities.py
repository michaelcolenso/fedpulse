import sqlite3
import unittest

from fedpulse.opportunities import rank_opportunities


class OpportunitiesTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript("""
            CREATE TABLE government_events (
              event_id TEXT PRIMARY KEY, source TEXT, source_id TEXT, kind TEXT, stage TEXT,
              title TEXT, agency TEXT, event_date TEXT, amount REAL, currency TEXT,
              official_url TEXT, payload_json TEXT, last_seen TEXT DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE government_identifiers (event_id TEXT, namespace TEXT, value TEXT);
        """)

    def add(self, event_id, title, date, *, naics=None, agency="AGRICULTURE, DEPARTMENT OF", amount=None, payload="{}"):
        self.conn.execute(
            "INSERT INTO government_events(event_id,source,source_id,kind,stage,title,agency,event_date,amount,currency,official_url,payload_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (event_id,"sam_opportunity",event_id,"contract_opportunity","Solicitation",title,agency,date,amount,"USD","https://sam.gov/test",payload),
        )
        if naics:
            self.conn.execute("INSERT INTO government_identifiers VALUES (?,?,?)", (event_id,"naics",naics))

    def test_relevant_construction_item_outranks_generic_fresh_item(self):
        self.add("roof", "Roof repairs in Seattle Washington", "2026-08-15", naics="238160", amount=600000,
                 payload='{"row":{"ResponseDeadLine":"2026-08-20"}}')
        self.add("generic", "Office software renewal", "2026-08-16", amount=5000000)
        items = rank_opportunities(self.conn, "2026-08-16")
        self.assertEqual(items[0]["event_id"], "roof")
        self.assertGreater(items[0]["score"], 80)
        self.assertTrue(any("NAICS" in reason for reason in items[0]["reasons"]))
        self.assertFalse(any(item["event_id"] == "generic" for item in items))

    def test_old_bulk_records_are_not_today_opportunities(self):
        self.add("old", "Historic construction grant", "2014-08-15", naics="236220")
        self.assertEqual(rank_opportunities(self.conn, "2026-08-16"), [])


if __name__ == "__main__":
    unittest.main()
