import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tests.v2_helpers import load_case, temp_db, seed_records
from fedpulse.normalize_agencies import normalize_all
from fedpulse.outputs_v2 import atomic_write_json, build_brief, build_v2_outputs, render_text_brief, validate_snapshot
from fedpulse.watchlist import detect_standalone

class TestOutputs(unittest.TestCase):
    def test_snapshot_validation_rejects_mixed_generation(self):
        payloads={name:{"schema_version":2,"as_of":"2026-08-06","generated_at":"2026-08-07T00:00:00Z","source_freshness":{},"items":[]} for name in ("daily_activity","packages","standalone","fr_metrics","marc_horizon","health","brief")}
        payloads["packages"]["generated_at"]="2026-08-08T00:00:00Z"
        with self.assertRaisesRegex(ValueError,"inconsistent generated_at"): validate_snapshot(payloads)

    def test_atomic_write_and_contracts(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/"x.json"; atomic_write_json(path,{"ok":1}); self.assertEqual(json.loads(path.read_text())["ok"],1)
            class Bad:
                def __iter__(self): raise RuntimeError("serialize")
            old=path.read_text()
            with self.assertRaises(Exception): atomic_write_json(path,{"bad":Bad()})
            self.assertEqual(path.read_text(),old)

    def test_v2_outputs_include_all_files_and_metadata(self):
        with temp_db() as conn, tempfile.TemporaryDirectory() as td:
            rows=load_case("ncua_package")+load_case("nist_standalone")
            seed_records(conn,rows); normalize_all(conn)
            out=build_v2_outputs(conn,"2026-08-06",Path(td),datetime(2026,8,7,tzinfo=timezone.utc))
            for name in ("daily_activity","packages","standalone","fr_metrics","marc_horizon","health","brief"):
                payload=out[name]; self.assertEqual(payload["schema_version"],2); self.assertIn("items",payload); self.assertEqual(payload["as_of_timezone"],"America/New_York")
                self.assertTrue((Path(td)/(name+".json")).exists())

    def test_failed_snapshot_stage_keeps_previous_generation_and_lifecycle(self):
        from unittest.mock import patch
        with temp_db() as conn, tempfile.TemporaryDirectory() as td:
            seed_records(conn,load_case("ncua_package")); normalize_all(conn)
            out=Path(td)
            build_v2_outputs(conn,"2026-08-06",out,datetime(2026,8,7,tzinfo=timezone.utc))
            before_target=(out/"current").readlink()
            before_state=conn.execute("select last_seen from signal_state where signal_type='package'").fetchone()[0]
            real=atomic_write_json; calls=0
            def fail_third(path,payload):
                nonlocal calls
                calls += 1
                if calls == 3: raise OSError("disk full")
                return real(path,payload)
            with patch("fedpulse.outputs_v2.atomic_write_json",side_effect=fail_third):
                with self.assertRaises(OSError):
                    build_v2_outputs(conn,"2026-08-06",out,datetime(2026,8,8,tzinfo=timezone.utc))
            self.assertEqual((out/"current").readlink(),before_target)
            self.assertEqual(conn.execute("select last_seen from signal_state where signal_type='package'").fetchone()[0],before_state)

class TestDigest(unittest.TestCase):
    def test_standalone_exact_rule_and_quiet_day_brief(self):
        with temp_db() as conn:
            seed_records(conn,load_case("nist_standalone")); normalize_all(conn)
            item=detect_standalone(conn,"2026-08-06")[0]
            self.assertTrue(item["matches"]); self.assertIn("rule",item["matches"][0])
        brief=build_brief({"health":{"items":[]},"daily_activity":{"items":[{"count":0}]},"packages":{"items":[]},"standalone":{"items":[]},"fr_metrics":{"items":[]},"marc_horizon":{"items":[]}})
        text=render_text_brief(brief)
        self.assertTrue(text.strip()); self.assertIn("TODAY",text)
        self.assertNotIn("low",text.lower())

    def test_low_confidence_packages_are_dashboard_only(self):
        brief = build_brief({"health":{"source_freshness":{}},"daily_activity":{"items":[]},"packages":{"items":[{"package_id":"low-1","confidence":"low","label":"uncertain"}]},"standalone":{"items":[]},"fr_metrics":{"items":[]},"marc_horizon":{"items":[]}})
        self.assertFalse(any(section["section"] == "high_medium_packages" for section in brief["items"]))

    def test_low_confidence_package_never_becomes_notifiable_state(self):
        from fedpulse.outputs_v2 import _apply_lifecycle
        with temp_db() as conn:
            payloads={"packages":{"items":[{"package_id":"low-1","confidence":"low","label":"uncertain"}]},"standalone":{"items":[]},"fr_metrics":{"items":[]},"marc_horizon":{"items":[]}}
            _apply_lifecycle(conn,payloads,datetime(2026,8,7,tzinfo=timezone.utc))
            self.assertFalse(payloads["packages"]["items"][0]["notify"])
            self.assertIsNone(conn.execute("select 1 from signal_state where signal_key='package:low-1'").fetchone())

    def test_brief_includes_only_notifiable_metric_rows(self):
        payload={"metric":"weekly_activity_spike","items":[
            {"agency":"new","alert":True,"notify":True,"lifecycle":"new","weekly_series":[{"week":"2026-08-03","count":99}]},
            {"agency":"continuing","alert":True,"notify":False,"lifecycle":"continuing"},
        ]}
        brief=build_brief({"health":{"source_freshness":{}},"daily_activity":{"items":[]},"packages":{"items":[]},"standalone":{"items":[]},"fr_metrics":{"items":[payload]},"marc_horizon":{"items":[]}})
        sections=[s for s in brief["items"] if s["section"] == "supporting_metrics"]
        self.assertEqual(len(sections),1)
        self.assertEqual([x["agency"] for x in sections[0]["items"][0]["items"]],["new"])
        self.assertNotIn("weekly_series",sections[0]["items"][0]["items"][0])

if __name__ == "__main__": unittest.main()
