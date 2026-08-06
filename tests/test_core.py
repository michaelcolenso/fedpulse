"""Unit tests — stdlib unittest (no network, no third-party deps).

Run: uv run python -m unittest discover -s tests -v
"""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fedpulse import db, fr_client, indices, marc_parser  # noqa: E402

MARCXML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<record xmlns="http://www.loc.gov/MARC21/slim">
  <leader>     nam a22     i 4500</leader>
  <controlfield tag="001">001234567</controlfield>
  <controlfield tag="005">20240115120000.0</controlfield>
  <controlfield tag="008">240115s2024    dcua     b   f000 0 eng d</controlfield>
  <datafield tag="110" ind1="1" ind2=" ">
    <subfield code="a">United States. Environmental Protection Agency.</subfield>
  </datafield>
  <datafield tag="245" ind1="1" ind2="0">
    <subfield code="a">National Primary Drinking Water Regulations for PFAS.</subfield>
  </datafield>
  <datafield tag="086" ind1="0" ind2=" ">
    <subfield code="a">EP 2.2:P 49/2</subfield>
  </datafield>
  <datafield tag="650" ind1=" " ind2="0">
    <subfield code="a">Perfluorinated chemicals</subfield>
    <subfield code="x">Law and legislation</subfield>
  </datafield>
  <datafield tag="650" ind1=" " ind2="0">
    <subfield code="a">Drinking water</subfield>
    <subfield code="x">Standards</subfield>
  </datafield>
  <datafield tag="856" ind1="4" ind2="0">
    <subfield code="u">https://purl.fdlp.gov/GPO/gpo123456</subfield>
  </datafield>
</record>
"""

MARC_BINARY_SAMPLE = None  # built in test


def build_binary_marc() -> bytes:
    """Build a minimal binary MARC21 record: 001, 110, 650."""
    rec_id = b"009999999"
    agency = b"United States. Department of Energy."
    subj = b"Direct air capture"
    fields = [
        (b"001", b"", rec_id),
        (b"110", b"1 ", b"\x1fa" + agency),
        (b"650", b" 0", b"\x1fa" + subj),
    ]
    directory = b""
    body = b""
    for tag, inds, data in fields:
        if inds:
            data = (inds.encode() if isinstance(inds, str) else inds) + data
        body += data
        directory += tag + f"{len(data):04d}{len(body) - len(data):05d}".encode()
    leader = f"{24 + len(directory) + len(body):05d}".encode()
    base = 24 + len(directory)
    leader += b"nam a22" + f"{base:05d}".encode() + b"   4500"  # full 24-byte leader
    return leader + directory + body + b"\x1d"


class TestMarcParser(unittest.TestCase):
    def test_marcxml_extraction(self):
        parsed = marc_parser.parse_marcxml(MARCXML_SAMPLE)
        self.assertEqual(len(parsed), 1)
        rec = marc_parser.normalize_record(parsed[0])
        assert rec is not None
        self.assertEqual(rec["id"], "marc:001234567")
        self.assertEqual(rec["title"], "National Primary Drinking Water Regulations for PFAS.")
        self.assertEqual(rec["sudoc"], "EP 2.2:P 49/2")
        self.assertEqual(rec["sudoc_stem"], "EP")
        self.assertIn("Environmental Protection Agency", rec["agency"])
        self.assertEqual(rec["subjects"], [
            "Perfluorinated chemicals--Law and legislation",
            "Drinking water--Standards",
        ])
        self.assertEqual(rec["url"], "https://purl.fdlp.gov/GPO/gpo123456")
        self.assertEqual(rec["cataloged_date"], "2024-01-15")
        self.assertEqual(rec["publication_date"], "2024-01-01")

    def test_binary_marc_extraction(self):
        raw = build_binary_marc()
        parsed = marc_parser.parse_marc_binary(raw)
        self.assertEqual(len(parsed), 1)
        rec = marc_parser.normalize_record(parsed[0])
        assert rec is not None
        self.assertEqual(rec["id"], "marc:009999999")
        self.assertIn("Department of Energy", rec["agency"])
        self.assertEqual(rec["subjects"], ["Direct air capture"])

    def test_xxe_guard(self):
        evil = MARCXML_SAMPLE.replace("<record ", "<!DOCTYPE foo [<!ENTITY xxe SYSTEM 'file:///etc/passwd'>]><record ")
        with self.assertRaises(ValueError):
            marc_parser.parse_marcxml(evil)


class TestIndices(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.conn = db.connect(Path(self.tmp) / "t.db")
        db.init_db(self.conn)

    def tearDown(self):
        self.conn.close()

    def seed(self, rows):
        for r in rows:
            db.upsert_record(self.conn, r)
        self.conn.commit()

    def test_api_zscore_flags_spike(self):
        # EPA: 12 weeks of ~2/week, then a 10-count week → should flag.
        import datetime as dt
        rows = []
        base = dt.date(2026, 1, 1)
        for i in range(12):
            w = base + dt.timedelta(weeks=i)
            for _ in range(2):
                rows.append({"id": f"fr:e{i}{_}", "source": "fr", "agency": "Environmental Protection Agency",
                             "doc_type": "notice", "publication_date": w.isoformat(),
                             "cataloged_date": w.isoformat(), "subjects": []})
        spike_w = base + dt.timedelta(weeks=12)
        for _ in range(10):
            rows.append({"id": f"fr:s{_}", "source": "fr", "agency": "Environmental Protection Agency",
                         "doc_type": "notice", "publication_date": spike_w.isoformat(),
                         "cataloged_date": spike_w.isoformat(), "subjects": []})
        self.seed(rows)
        api = indices.compute_api(self.conn, as_of=spike_w.isoformat())
        epa = [a for a in api["agencies"] if a["agency"] == "Environmental Protection Agency"][0]
        self.assertTrue(epa["flagged"])
        self.assertGreaterEqual(epa["z_score"], indices.API_Z_THRESHOLD)

    def test_rcr_ratio(self):
        rows = []
        # 10 proposed + 20 notices + 3 finals → ratio 10
        for i in range(10):
            rows.append({"id": f"fr:p{i}", "source": "fr", "agency": "EPA",
                         "doc_type": "proposed rule", "publication_date": "2026-03-01",
                         "cataloged_date": "2026-03-01", "subjects": []})
        for i in range(20):
            rows.append({"id": f"fr:n{i}", "source": "fr", "agency": "EPA",
                         "doc_type": "notice", "publication_date": "2026-04-01",
                         "cataloged_date": "2026-04-01", "subjects": []})
        for i in range(3):
            rows.append({"id": f"fr:f{i}", "source": "fr", "agency": "EPA",
                         "doc_type": "rule", "publication_date": "2026-05-01",
                         "cataloged_date": "2026-05-01", "subjects": []})
        self.seed(rows)
        rcr = indices.compute_rcr(self.conn, as_of="2026-06-01")
        epa = [a for a in rcr["agencies"] if a["agency"] == "EPA"][0]
        self.assertEqual(epa["churn_ratio"], 10.0)
        self.assertTrue(epa["flagged"])

    def test_ter_new_and_accel(self):
        # old subject seen long ago; new subject in last 30d
        import datetime as dt
        base = dt.date(2026, 1, 1)
        rows = []
        # subject A: 5 occurrences 10 weeks ago
        for i in range(5):
            rows.append({"id": f"fr:a{i}", "source": "fr", "agency": "X",
                         "doc_type": "notice", "publication_date": (base + dt.timedelta(weeks=10)).isoformat(),
                         "cataloged_date": (base + dt.timedelta(weeks=10)).isoformat(),
                         "subjects": ["Old topic"]})
        # subject B: new in last 30 days
        rows.append({"id": "fr:new1", "source": "fr", "agency": "DOE",
                     "doc_type": "notice", "publication_date": (base + dt.timedelta(days=5)).isoformat(),
                     "cataloged_date": (base + dt.timedelta(days=5)).isoformat(),
                     "subjects": ["Direct air capture"]})
        self.seed(rows)
        for r in rows:
            db.note_subjects(self.conn, r["id"], r["cataloged_date"], r["agency"], r["subjects"])
        self.conn.commit()
        ter = indices.compute_ter(self.conn, as_of=(base + dt.timedelta(days=30)).isoformat())
        new = [s for s in ter["new_subjects"] if s["subject"] == "Direct air capture"]
        self.assertEqual(len(new), 1)


class TestFRMapping(unittest.TestCase):
    def test_to_record_keeps_valid_ids(self):
        doc = {
            "document_number": "2026-16015",
            "type": "Rule",
            "title": "Example rule",
            "publication_date": "2026-08-05",
            "agencies": [{"name": "Environmental Protection Agency", "slug": "environmental-protection-agency"}],
            "topics": ["Drinking water"],
            "citation": "91 FR 50659",
            "html_url": "https://example.gov/x",
        }
        rec = fr_client.to_record(doc)
        self.assertEqual(rec["id"], "fr:2026-16015")
        self.assertFalse(rec["id"].endswith(":"))  # must NOT be treated as malformed
        self.assertEqual(rec["doc_type"], "rule")
        self.assertEqual(rec["agency"], "Environmental Protection Agency")

    def test_malformed_id_detected(self):
        rec = fr_client.to_record({"document_number": None})
        self.assertTrue(rec["id"].endswith(":"))  # the ingest guard skips these


if __name__ == "__main__":
    unittest.main()
