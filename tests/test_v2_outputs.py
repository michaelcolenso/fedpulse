import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tests.v2_helpers import load_case, temp_db, seed_records
from fedpulse.normalize_agencies import normalize_all
from fedpulse.outputs_v2 import atomic_write_json, build_brief, build_v2_outputs, render_text_brief
from fedpulse.watchlist import detect_standalone

class TestOutputs(unittest.TestCase):
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

    def test_brief_includes_only_notifiable_metric_rows(self):
        payload={"metric":"weekly_activity_spike","items":[
            {"agency":"new","alert":True,"notify":True,"lifecycle":"new"},
            {"agency":"continuing","alert":True,"notify":False,"lifecycle":"continuing"},
        ]}
        brief=build_brief({"health":{"source_freshness":{}},"daily_activity":{"items":[]},"packages":{"items":[]},"standalone":{"items":[]},"fr_metrics":{"items":[payload]},"marc_horizon":{"items":[]}})
        sections=[s for s in brief["items"] if s["section"] == "supporting_metrics"]
        self.assertEqual(len(sections),1)
        self.assertEqual([x["agency"] for x in sections[0]["items"][0]["items"]],["new"])

if __name__ == "__main__": unittest.main()
