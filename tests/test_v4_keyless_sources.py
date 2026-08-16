import io
import sqlite3
import unittest
import zipfile

from fedpulse import db
from fedpulse.action_graph import GovernmentEvent, link_exact_identifiers, upsert_events
from fedpulse.congress_bulk_client import parse_bill, updated_bill_urls
from fedpulse.grants_client import discover_latest_extract, parse_extract
from fedpulse.oira_meetings_client import detail_urls, parse_detail
from fedpulse.sam_opportunities_client import parse_csv
from fedpulse.usaspending_client import normalize_award


class TestV4KeylessSources(unittest.TestCase):
    def test_graph_links_exact_rin_but_not_shared_program(self):
        conn = sqlite3.connect(":memory:"); conn.row_factory = sqlite3.Row; db.init_db(conn)
        events = [
            GovernmentEvent("unified_agenda","a","regulatory_plan",identifiers=(("rin","1000-AA01"),("assistance_listing","10.001"))),
            GovernmentEvent("oira_pending","b","oira_review",identifiers=(("rin","1000-AA01"),)),
            GovernmentEvent("grants","c","funding_opportunity",identifiers=(("assistance_listing","10.001"),)),
        ]
        upsert_events(conn, events); created = link_exact_identifiers(conn)
        self.assertEqual(created, 1)
        edge = conn.execute("select * from government_edges").fetchone()
        self.assertEqual(edge["method"], "exact:rin")

    def test_oira_meeting_discovery_and_parse(self):
        search = '<a href="/public/do/viewEO12866Meeting?meetingId=123&viewRule=false">meeting</a>'
        urls = detail_urls(search); self.assertEqual(len(urls), 1)
        page = """<html><body>RIN: 0910-AJ02 Title: Substances Generally Recognized as Safe Agency/Subagency: HHS / FDA Stage of Rulemaking: Proposed Rule Stage Meeting Date/Time: 12/18/2025 01:30 PM Requestor: Example Group Requestor's Name: Jane</body></html>"""
        event = parse_detail(page, urls[0])
        self.assertEqual(event.source_id, "123"); self.assertIn(("rin","0910-AJ02"), event.identifiers)

    def test_grants_enhanced_extract(self):
        html = '<a href="https://example.gov/GrantsDBExtract20260815v2.zip">old</a><a href="https://example.gov/GrantsDBExtract20260816v2.zip">new</a>'
        self.assertIn("20260816", discover_latest_extract(html))
        xml = b"""<Grants><Opportunity><OpportunityID>123</OpportunityID><OpportunityNumber>ABC-1</OpportunityNumber><OpportunityTitle>Grid modernization</OpportunityTitle><AgencyName>DOE</AgencyName><ForecastedPostDate>2026-10-01</ForecastedPostDate><EstimatedTotalProgramFunding>450000000</EstimatedTotalProgramFunding><CFDANumbers>81.001</CFDANumbers></Opportunity></Grants>"""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf,"w") as zf: zf.writestr("GrantsDBExtract.xml", xml)
        events = parse_extract(buf.getvalue()); self.assertEqual(len(events), 1)
        self.assertEqual(events[0].stage, "forecast"); self.assertEqual(events[0].amount, 450000000.0)

    def test_usaspending_normalization(self):
        event = normalize_award({"Award ID":"CONT_AWD_123","Recipient Name":"Acme","Award Amount":1200000,"Awarding Agency":"DOE","Start Date":"2026-08-15","Description":"Grid award","CFDA Number":"81.001"})
        self.assertEqual(event.kind,"federal_award"); self.assertEqual(event.amount,1200000.0)
        self.assertIn(("assistance_listing","81.001"), event.identifiers)

    def test_sam_csv(self):
        body = b"NoticeId,Title,Solicitation Number,Department/Ind.Agency,PostedDate,Type,NaicsCode\nN1,Bridge repair,W912-26-R-1,ARMY,2026-08-15,Presolicitation,237310\n"
        events = parse_csv(body); self.assertEqual(len(events),1)
        self.assertIn(("solicitation","W912-26-R-1"), events[0].identifiers)

    def test_bill_status_rss_and_xml(self):
        rss = b"<rss><description>https://www.govinfo.gov/bulkdata/BILLSTATUS/119/hr/BILLSTATUS-119hr42.xml</description></rss>"
        urls = updated_bill_urls(rss); self.assertEqual(len(urls),1)
        xml = b"""<billStatus><bill><number>42</number><type>HR</type><congress>119</congress><introducedDate>2025-01-10</introducedDate><titles><item><title>Example Act</title></item></titles><actions><item><actionDate>2026-08-15</actionDate><text>Passed House</text></item></actions></bill></billStatus>"""
        event = parse_bill(xml, urls[0]); self.assertEqual(event.source_id,"119:hr:42")
        self.assertIn(("bill","119:hr:42"), event.identifiers)


if __name__ == "__main__": unittest.main()
