import json
import unittest
from pathlib import Path
from tests.v2_helpers import temp_db
from fedpulse.backtest import EVENTS, check, evaluate_events

class TestEvaluation(unittest.TestCase):
    def test_preregistered_events_include_cfpb_lead_and_negative_controls(self):
        event = next(x for x in EVENTS if x["name"].startswith("CFPB"))
        self.assertEqual(event["signal_class"], "predictive")
        self.assertGreaterEqual(event["lead_days_required"], 30)
        self.assertTrue(event["negative_controls"])

    def test_post_event_ter_evidence_is_rejected(self):
        with temp_db() as conn:
            conn.execute("insert into subject_first_seen(subject, first_seen_date, first_record_id, first_agency) values (?,?,?,?)", ("Post event subject", "2024-04-11", "marc:1", "Agency"))
            conn.commit()
            result = check(conn, {"name":"event","event_date":"2024-04-10","signal_class":"horizon","index":"ter","subject":"Post event subject","lead_days_required":0,"negative_controls":[]})
            self.assertFalse(result["fired"])
            self.assertIn("after the event", result["detail"])

    def test_predictive_and_horizon_reports_are_separate_and_metrics_are_honest(self):
        with temp_db() as conn:
            report = evaluate_events(conn, [{"name":"empty predictive","event_date":"2024-01-01","signal_class":"predictive","index":"api","agency":"Missing","lead_days_required":30,"negative_controls":[]}, {"name":"empty horizon","event_date":"2024-01-01","signal_class":"horizon","index":"ter","subject":"Missing","lead_days_required":0,"negative_controls":[]}])
            self.assertIn("precision", report["predictive"])
            self.assertIn("recall", report["predictive"])
            self.assertIn("false_positive_rate", report["predictive"])
            self.assertIn("horizon", report)
            self.assertEqual(report["horizon"]["events"][0]["signal_class"], "horizon")

if __name__ == "__main__": unittest.main()
