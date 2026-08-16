import sqlite3
import unittest
from fedpulse.opportunities import lane_for, load_profiles, rank_opportunities

class OpportunitiesTests(unittest.TestCase):
    def setUp(self):
        self.conn=sqlite3.connect(":memory:"); self.conn.row_factory=sqlite3.Row
        self.conn.executescript("""CREATE TABLE government_events (event_id TEXT PRIMARY KEY, source TEXT, source_id TEXT, kind TEXT, stage TEXT,title TEXT, agency TEXT, event_date TEXT, amount REAL, currency TEXT,official_url TEXT, payload_json TEXT, last_seen TEXT DEFAULT CURRENT_TIMESTAMP);CREATE TABLE government_identifiers (event_id TEXT, namespace TEXT, value TEXT);""")
    def add(self,event_id,title,date,*,naics=None,agency="AGRICULTURE, DEPARTMENT OF",amount=None,payload="{}",kind="contract_opportunity"):
        self.conn.execute("INSERT INTO government_events(event_id,source,source_id,kind,stage,title,agency,event_date,amount,currency,official_url,payload_json) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",(event_id,"sam_opportunity",event_id,kind,"Solicitation",title,agency,date,amount,"USD","https://sam.gov/test",payload))
        if naics:self.conn.execute("INSERT INTO government_identifiers VALUES (?,?,?)",(event_id,"naics",naics))
    def test_relevant_construction_item_outranks_generic_fresh_item(self):
        self.add("roof","Roof repairs in Seattle Washington","2026-08-15",naics="238160",amount=600000,payload='{"row":{"ResponseDeadLine":"2026-08-20"}}'); self.add("generic","Office software renewal","2026-08-16",amount=5000000)
        items=rank_opportunities(self.conn,"2026-08-16"); self.assertEqual(items[0]["event_id"],"roof"); self.assertEqual(items[0]["lane"],"act_now"); self.assertFalse(any(x["event_id"]=="generic" for x in items))
    def test_old_bulk_records_are_not_today_opportunities(self):
        self.add("old","Historic construction grant","2014-08-15",naics="236220"); self.assertEqual(rank_opportunities(self.conn,"2026-08-16"),[])
    def test_lanes_are_action_semantic(self):
        self.assertEqual(lane_for("contract_opportunity",4),"act_now"); self.assertEqual(lane_for("federal_award_action",None),"market_intelligence"); self.assertEqual(lane_for("legislative_update",None),"policy_signals")
    def test_expanded_profiles_exist(self):
        profiles=load_profiles(); self.assertTrue({"default","ai_technology","business_opportunities","pnw_intelligence"}.issubset(profiles))
if __name__=="__main__": unittest.main()
