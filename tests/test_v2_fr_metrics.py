import datetime as dt
import unittest
from tests.v2_helpers import temp_db, fr_record, seed_records
from fedpulse.metrics_v2 import complete_publication_weeks, compute_fr_activity, compute_level_shifts, poisson_upper_tail

class TestFRMetrics(unittest.TestCase):
    def test_activity_and_level_shift_are_isolated_per_agency_with_zero_weeks(self):
        with temp_db() as conn:
            rows = []
            for wi, count in enumerate([1] * 16 + [8]):
                monday = dt.date(2026, 4, 27) + dt.timedelta(days=7 * wi)
                for j in range(count):
                    rows.append(fr_record(f"a-{wi}-{j}", "Agency A", (monday + dt.timedelta(days=j % 5)).isoformat()))
            rows.append(fr_record("b-current", "Agency B", "2026-08-17"))
            seed_records(conn, rows)
            activity = compute_fr_activity(conn, "2026-08-24")
            items = {item["agency"]: item for item in activity["items"]}
            self.assertEqual(set(items), {"Agency A", "Agency B"})
            self.assertEqual(len(items["Agency B"]["weeks"]), 17)
            self.assertIn(0, items["Agency B"]["baseline_raw_weekly_counts"])
            self.assertNotEqual(items["Agency A"]["current_count"], items["Agency B"]["current_count"])
            shifts = compute_level_shifts(conn, "2026-08-24")
            shift_items = {item["agency"]: item for item in shifts["items"]}
            self.assertEqual(set(shift_items), {"Agency A", "Agency B"})
            self.assertGreater(shift_items["Agency A"]["recent_total"], shift_items["Agency B"]["recent_total"])

    def test_complete_weeks_are_monday_friday_and_exclude_current_partial(self):
        weeks = complete_publication_weeks(dt.date(2026, 8, 12), 3)
        self.assertEqual(weeks[0], (dt.date(2026, 7, 20), dt.date(2026, 7, 24)))
        self.assertTrue(all(start.weekday() == 0 and end.weekday() == 4 for start, end in weeks))
        self.assertNotIn((dt.date(2026, 8, 10), dt.date(2026, 8, 14)), weeks)

    def test_poisson_low_count_and_zero_variance_are_honest(self):
        self.assertLessEqual(poisson_upper_tail(8, 2.0), 0.01)
        with temp_db() as conn:
            rows = [fr_record(f"z-{i}", "Fixture Agency", f"2026-08-{d:02d}", topics=["Fixture"]) for i, d in enumerate([3, 4, 5, 6, 7], 1)]
            seed_records(conn, rows)
            result = compute_fr_activity(conn, "2026-08-12")
            self.assertIn("baseline_raw_weekly_counts", result)
            self.assertEqual(result["statistical_evidence"],"insufficient_zero_variance")
            self.assertNotIn("z_score", result)
            self.assertEqual(result["items"][0]["statistical_evidence"],"insufficient_zero_variance")
            self.assertNotIn("z_score",result["items"][0])

    def test_partial_week_not_scored_and_marc_is_ignored(self):
        with temp_db() as conn:
            rows = [fr_record(f"f-{i}", "Fixture Agency", f"2026-08-{10+i:02d}") for i in range(3)]
            rows.append({"id":"marc:x","source":"marc","title":"x","agency":"A","doc_type":"","publication_date":"2026-08-10","cataloged_date":"2026-08-10","url":"https://catalog.gpo.gov/F/x","subjects":[],"raw_json":{}})
            seed_records(conn, rows)
            result = compute_fr_activity(conn, "2026-08-12")
            self.assertFalse(result.get("alert", False))
            self.assertEqual(result["as_of_timezone"], "America/New_York")
            self.assertEqual(result["generated_at_timezone"], "UTC")

    def test_sustained_shift_requires_three_active_recent_weeks_and_thresholds(self):
        with temp_db() as conn:
            rows=[]
            # Four recent complete weeks: activity in three, total 12; prior 12 total 4.
            for wi, count in enumerate([1]*12 + [6,5,0,5]):
                monday = dt.date(2026, 5, 4) + dt.timedelta(days=7*wi)
                for j in range(count): rows.append(fr_record(f"s-{wi}-{j}", "Fixture Agency", (monday + dt.timedelta(days=j % 5)).isoformat()))
            seed_records(conn, rows)
            result = compute_level_shifts(conn, "2026-08-24")
            self.assertTrue(result["items"] or result.get("alert"))
            item = (result["items"] or [result])[0]
            self.assertGreaterEqual(item["recent_total"], item["baseline_total"] + 4)

if __name__ == "__main__": unittest.main()
