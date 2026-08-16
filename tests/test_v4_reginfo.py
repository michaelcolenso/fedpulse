import unittest

from fedpulse.reginfo_client import RegInfoError, parse_oira


class TestRegInfoClient(unittest.TestCase):
    def test_parses_oira_record_without_credentials(self):
        xml = b"""<?xml version='1.0'?>
        <ROOT><RULE>
          <RIN>3235-AN57</RIN>
          <TITLE>Electronic Delivery of Information</TITLE>
          <AGENCY>SEC</AGENCY>
          <STAGE>Proposed Rule</STAGE>
          <STATUS>Pending Review</STATUS>
          <RECEIVED_DATE>06/22/2026</RECEIVED_DATE>
        </RULE></ROOT>"""
        rows = parse_oira(xml, source="oira_pending", source_url="https://example.gov/feed.xml")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row.rin, "3235-AN57")
        self.assertEqual(row.stage, "Proposed Rule")
        self.assertEqual(row.status, "Pending Review")
        self.assertEqual(row.source, "oira_pending")
        self.assertEqual(len(row.raw_sha256), 64)

    def test_rejects_non_xml_and_malformed_xml(self):
        with self.assertRaises(RegInfoError):
            parse_oira(b"not xml", source="x", source_url="https://example.gov/x")
        with self.assertRaises(RegInfoError):
            parse_oira(b"<ROOT>", source="x", source_url="https://example.gov/x")

    def test_deduplicates_nested_candidates(self):
        xml = b"""<ROOT><RULE><RIN>1000-AA01</RIN><TITLE>Example</TITLE><DETAIL><RIN>1000-AA01</RIN><TITLE>Example</TITLE></DETAIL></RULE></ROOT>"""
        rows = parse_oira(xml, source="oira_pending", source_url="https://example.gov/feed.xml")
        self.assertEqual(len(rows), 1)


if __name__ == "__main__":
    unittest.main()
