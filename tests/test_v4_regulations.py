import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path

from fedpulse import db, regulations_client
from fedpulse.pipeline_v2 import run_pipeline
from fedpulse.regulatory_lifecycle import build_lifecycles, infer_stage, link_fr_documents, upsert_regulations_document


class TestRegulationsV4(unittest.TestCase):
    def test_normalize_document(self):
        row = regulations_client.normalize_document({"id":"EPA-HQ-OAR-2026-0001-0001","attributes":{"docketId":"EPA-HQ-OAR-2026-0001","agencyId":"EPA","documentType":"Proposed Rule","title":"Test","postedDate":"2026-08-15T12:00:00Z","commentEndDate":"2026-09-15T23:59:59Z","frDocNum":"2026-12345"}})
        self.assertEqual(row["document_id"], "EPA-HQ-OAR-2026-0001-0001")
        self.assertEqual(row["fr_doc_number"], "2026-12345")
        self.assertEqual(row["docket_id"], "EPA-HQ-OAR-2026-0001")

    def test_stage_inference(self):
        self.assertEqual(infer_stage("Proposed Rule", comment_end_date="2026-09-01", as_of="2026-08-16"), "proposal_open")
        self.assertEqual(infer_stage("Proposed Rule", comment_end_date="2026-08-01", as_of="2026-08-16"), "comments_closed")
        self.assertEqual(infer_stage("Rule", as_of="2026-08-16"), "final_published")
        self.assertEqual(infer_stage("Rule", withdrawn=True, as_of="2026-08-16"), "withdrawn")

    def test_explicit_fr_link_and_lifecycle(self):
        with tempfile.TemporaryDirectory() as td:
            conn = db.connect(Path(td)/"x.db"); db.init_db(conn)
            db.upsert_record(conn,{"id":"fr:2026-12345","source":"fr","title":"FR proposal","agency":"EPA","doc_type":"proposed_rule","publication_date":"2026-08-15","cataloged_date":"2026-08-15","url":"https://example.test/fr","subjects":[],"raw_json":{"docket_ids":["EPA-HQ-OAR-2026-0001"]}})
            upsert_regulations_document(conn,{"document_id":"EPA-HQ-OAR-2026-0001-0001","docket_id":"EPA-HQ-OAR-2026-0001","agency_id":"EPA","document_type":"Proposed Rule","title":"Proposal","posted_date":"2026-08-15T12:00:00Z","comment_end_date":"2026-09-15T23:59:59Z","fr_doc_number":"2026-12345","raw_json":{}})
            self.assertEqual(link_fr_documents(conn), 1)
            life = build_lifecycles(conn,"2026-08-16")
            self.assertEqual(life[0]["stage"], "proposal_open")
            self.assertEqual(life[0]["events"][0]["fr_record_ids"], ["fr:2026-12345"])
            conn.close()

    def test_pipeline_regulations_is_optional_and_injectable(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td); dbp=root/"x.db"; out=root/"out"
            regs=[{"document_id":"EPA-HQ-OAR-2026-0001-0001","docket_id":"EPA-HQ-OAR-2026-0001","agency_id":"EPA","document_type":"Proposed Rule","title":"Proposal","posted_date":"2026-08-15T12:00:00Z","comment_end_date":"2026-09-15T23:59:59Z","raw_json":{}}]
            code=run_pipeline(dbp,out,"2026-08-16",ingest_fr=False,sync_marc=False,regulations_fetcher=lambda: regs,now=dt.datetime(2026,8,16,tzinfo=dt.timezone.utc))
            self.assertEqual(code,0)
            conn=db.connect(dbp)
            self.assertEqual(conn.execute("select count(*) from regulations_documents").fetchone()[0],1)
            self.assertEqual(conn.execute("select stage from regulatory_lifecycles").fetchone()[0],"proposal_open")
            conn.close()

if __name__ == "__main__": unittest.main()
