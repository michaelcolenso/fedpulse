import sqlite3
import unittest
from fedpulse.hidden_gems import detect_hidden_gems

class HiddenGemTests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(":memory:"); self.conn.row_factory=sqlite3.Row
        self.conn.executescript("""CREATE TABLE government_events (event_id TEXT PRIMARY KEY,source TEXT,source_id TEXT,kind TEXT,stage TEXT,title TEXT,agency TEXT,event_date TEXT,amount REAL,currency TEXT,official_url TEXT,payload_json TEXT,first_seen TEXT,last_seen TEXT);CREATE TABLE government_identifiers (event_id TEXT,namespace TEXT,value TEXT);""")
    def add(self,event_id,date,title,agency="Army Corps of Engineers",naics="237990",stage="Solicitation",payload="{}",first_seen="2026-08-16"):
        self.conn.execute("INSERT INTO government_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(event_id,"sam_opportunity",event_id,"contract_opportunity",stage,title,agency,date,None,"USD","https://sam.gov/test",payload,first_seen+" 10:00:00",first_seen+" 10:00:00"))
        if naics:self.conn.execute("INSERT INTO government_identifiers VALUES (?,?,?)",(event_id,"naics",naics))
    def test_first_local_agency_naics_combination_surfaces(self):
        self.add("gem","2026-08-16","Seattle Washington marine construction sources sought",stage="Sources Sought",payload='{"row":{"SetAside":"Total Small Business Set-Aside"}}')
        gems=detect_hidden_gems(self.conn,"2026-08-16")
        self.assertEqual(gems[0]["event_id"],"gem")
        self.assertGreaterEqual(gems[0]["hidden_gem_components"]["first_combination"],18)
        self.assertGreaterEqual(gems[0]["hidden_gem_components"]["low_visibility_proxy"],16)
    def test_common_pattern_scores_below_new_combination(self):
        for i in range(4): self.add(f"old{i}",f"2026-07-{10+i:02d}","Washington construction work")
        self.add("common","2026-08-16","Washington construction solicitation")
        self.add("rare","2026-08-16","Seattle roof construction sources sought",naics="238160",stage="Sources Sought")
        gems=detect_hidden_gems(self.conn,"2026-08-16")
        self.assertEqual(gems[0]["event_id"],"rare")
    def test_irrelevant_rare_item_does_not_surface(self):
        self.add("irrelevant","2026-08-16","Medical laboratory reagent sources sought",agency="Health Agency",naics="325413",stage="Sources Sought")
        self.assertEqual(detect_hidden_gems(self.conn,"2026-08-16"),[])

if __name__=="__main__": unittest.main()
