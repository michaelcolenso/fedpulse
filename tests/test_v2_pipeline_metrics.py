import datetime as dt
import unittest
from tests.v2_helpers import temp_db, fr_record, seed_records
from fedpulse.lifecycle import fingerprint, should_notify, update_signal_state
from fedpulse.metrics_v2 import compute_pipeline_metrics, percentile_rank

class TestPipelineMetrics(unittest.TestCase):
    def test_primary_ratio_excludes_notices_and_small_samples_suppress(self):
        with temp_db() as conn:
            rows=[]
            for i in range(10): rows.append(fr_record(f"final-{i}", "Agency A", "2026-08-01", doc_type="rule"))
            for i in range(5): rows.append(fr_record(f"prop-{i}", "Agency A", "2026-08-01", doc_type="proposed_rule"))
            for i in range(50): rows.append(fr_record(f"notice-{i}", "Agency A", "2026-08-01", doc_type="notice"))
            rows.append(fr_record("small", "Agency B", "2026-08-01", doc_type="proposed_rule"))
            seed_records(conn, rows)
            result = compute_pipeline_metrics(conn, "2026-08-31")
            a = next(x for x in result["items"] if x["agency"] == "Agency A")
            self.assertEqual(a["proposal_to_final_ratio"], .5)
            self.assertEqual(a["activity_to_final_ratio"], 5.5)
            self.assertFalse(next(x for x in result["items"] if x["agency"] == "Agency B")["eligible"])

    def test_percentile_rank_and_zero_history_z_suppression(self):
        self.assertEqual(percentile_rank([1,2,3], 2), 50.0)
        with temp_db() as conn:
            rows=[fr_record(f"f-{i}", "Agency A", "2026-08-01", doc_type="rule") for i in range(10)]
            seed_records(conn, rows)
            item = compute_pipeline_metrics(conn, "2026-08-31")["items"][0]
            self.assertIsNone(item.get("history_z_score"))
            self.assertFalse(item.get("newly_elevated", False))

class TestLifecycle(unittest.TestCase):
    def test_score_only_fingerprint_is_stable(self):
        self.assertEqual(fingerprint({"signal_key":"x","signal_type":"package","direction":"reduce_or_rescind","confidence":"high","priority_score":1}), fingerprint({"signal_key":"x","signal_type":"package","direction":"reduce_or_rescind","confidence":"high","priority_score":99}))

    def test_new_continuing_resolved_and_cooldown(self):
        with temp_db() as conn:
            now=dt.datetime(2026,8,10,12,tzinfo=dt.timezone.utc)
            first=update_signal_state(conn,[{"signal_key":"p","signal_type":"package","status":"qualified","direction":"reduce_or_rescind","confidence":"high","payload":{"x":1}}],now)
            self.assertEqual(first[0]["lifecycle"],"new"); self.assertTrue(first[0]["notify"])
            second=update_signal_state(conn,[{"signal_key":"p","signal_type":"package","status":"qualified","direction":"reduce_or_rescind","confidence":"high","payload":{"x":1}}],now+dt.timedelta(hours=1))
            self.assertEqual(second[0]["lifecycle"],"continuing"); self.assertFalse(second[0]["notify"])
            resolved=update_signal_state(conn,[],now+dt.timedelta(hours=2))
            self.assertEqual(resolved[0]["lifecycle"],"resolved")
            self.assertTrue(resolved[0]["notify"])
            state = conn.execute("select status, last_notified, fingerprint from signal_state where signal_key='p'").fetchone()
            self.assertEqual(state[0], "resolved")
            self.assertIsNotNone(state[1])
            self.assertEqual(update_signal_state(conn, [], now + dt.timedelta(hours=3)), [])

    def test_unchanged_continuing_does_not_notify_after_cooldown(self):
        with temp_db() as conn:
            now=dt.datetime(2026,8,10,12,tzinfo=dt.timezone.utc)
            signal={"signal_key":"p","signal_type":"package","status":"qualified","direction":"reduce_or_rescind","confidence":"high","payload":{"x":1}}
            update_signal_state(conn,[signal],now)
            later=update_signal_state(conn,[signal],now+dt.timedelta(hours=96))
            self.assertEqual(later[0]["lifecycle"],"continuing")
            self.assertFalse(later[0]["notify"])

    def test_stale_notifies_only_on_transition(self):
        with temp_db() as conn:
            now=dt.datetime(2026,8,10,12,tzinfo=dt.timezone.utc)
            signal={"signal_key":"p","signal_type":"metric","status":"qualified","confidence":"medium","payload":{"x":1}}
            update_signal_state(conn,[signal],now)
            stale={**signal,"status":"stale"}
            first=update_signal_state(conn,[stale],now+dt.timedelta(hours=1))
            second=update_signal_state(conn,[stale],now+dt.timedelta(hours=2))
            self.assertEqual(first[0]["lifecycle"],"stale")
            self.assertTrue(first[0]["notify"])
            self.assertEqual(second[0]["lifecycle"],"stale")
            self.assertFalse(second[0]["notify"])

    def test_direction_change_bypasses_cooldown(self):
        with temp_db() as conn:
            now=dt.datetime(2026,8,10,12,tzinfo=dt.timezone.utc)
            update_signal_state(conn,[{"signal_key":"p","signal_type":"package","status":"qualified","direction":"reduce_or_rescind","confidence":"high","payload":{}}],now)
            changed=update_signal_state(conn,[{"signal_key":"p","signal_type":"package","status":"qualified","direction":"increase_or_require","confidence":"high","payload":{}}],now+dt.timedelta(hours=1))
            self.assertTrue(changed[0]["notify"])

    def test_package_member_growth_waits_for_cooldown_then_notifies(self):
        with temp_db() as conn:
            now=dt.datetime(2026,8,10,12,tzinfo=dt.timezone.utc)
            first={"signal_key":"p","signal_type":"package","status":"qualified","direction":"reduce_or_rescind","confidence":"high","payload":{"evidence":[{"record_id":"a"}],"document_type_counts":{"notice":1}}}
            grown={**first,"payload":{"evidence":[{"record_id":"a"},{"record_id":"b"}],"document_type_counts":{"notice":2}}}
            update_signal_state(conn,[first],now)
            early=update_signal_state(conn,[grown],now+dt.timedelta(hours=1))
            self.assertFalse(early[0]["notify"])
            due=update_signal_state(conn,[grown],now+dt.timedelta(hours=49))
            self.assertTrue(due[0]["notify"])

if __name__ == "__main__": unittest.main()
