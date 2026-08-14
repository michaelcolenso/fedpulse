import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from tests.v2_helpers import load_case, seed_records, temp_db
from fedpulse.normalize_agencies import normalize_all
from fedpulse.outputs_v2 import build_v2_outputs


class TestV2Integration(unittest.TestCase):
    def test_temporary_db_golden_packages_standalone_lifecycle_and_all_outputs(self):
        with temp_db() as conn, tempfile.TemporaryDirectory() as td:
            seed_records(conn, load_case("ncua_package") + load_case("phmsa_package") + load_case("cdc_funding_package") + load_case("nist_standalone") + load_case("unrelated_same_day_notices") + load_case("small_marc_batch"))
            normalize_all(conn)
            out_dir = Path(td) / "outputs"
            first = build_v2_outputs(conn, "2026-08-06", out_dir, datetime(2026, 8, 7, tzinfo=timezone.utc))
            second = build_v2_outputs(conn, "2026-08-06", out_dir, datetime(2026, 8, 7, 1, tzinfo=timezone.utc))
            names = ("daily_activity", "packages", "standalone", "fr_metrics", "marc_horizon", "health", "brief")
            self.assertEqual(set(names), {p.stem for p in out_dir.glob("*.json")})
            for name in names:
                self.assertEqual(json.loads((out_dir / f"{name}.json").read_text())["schema_version"], 2)
            self.assertEqual(len(first["packages"]["items"]), 3)
            self.assertTrue(all((__import__("datetime").date.fromisoformat(p["date_end"]) - __import__("datetime").date.fromisoformat(p["date_start"])).days <= 2 for p in first["packages"]["items"]))
            self.assertFalse(any("unrelated" in p["package_id"] for p in first["packages"]["items"]))
            self.assertTrue(first["standalone"]["items"])
            self.assertTrue(first["packages"]["items"][0]["evidence"][0]["official_url"].startswith("https://"))
            self.assertEqual(first["packages"]["items"][0]["package_id"], second["packages"]["items"][0]["package_id"])
            self.assertEqual(first["packages"]["items"][0]["package_version_id"], second["packages"]["items"][0]["package_version_id"])
            self.assertTrue(first["standalone"]["items"][0]["taxonomy_versions"])
            self.assertIn("federal_register", first["health"]["source_freshness"])
            self.assertIn("marc", first["health"]["source_freshness"])
            state = conn.execute("select status, last_notified from signal_state where signal_type='package'").fetchone()
            self.assertEqual(state[0], "continuing")
            package = second["packages"]["items"][0]
            self.assertFalse(package["notify"])
            brief_packages = [x for section in second["brief"]["items"] if section["section"] == "high_medium_packages" for x in section["items"]]
            self.assertEqual(brief_packages, [], "unchanged continuing packages stay dashboard-only")
            low_horizon = [x for x in second["marc_horizon"]["items"] if x.get("confidence") not in {"high", "medium"}]
            brief_horizon = [x for section in second["brief"]["items"] if section["section"] == "marc_horizon" for x in section["items"]]
            self.assertFalse(set(map(lambda x: x.get("subject"), low_horizon)) & set(map(lambda x: x.get("subject"), brief_horizon)))

            package_ids=[p["package_id"] for p in second["packages"]["items"]]
            conn.execute("delete from records where source='fr' and id != 'fr:nist-1'")
            conn.commit()
            third=build_v2_outputs(conn,"2026-08-06",out_dir,datetime(2026,8,7,2,tzinfo=timezone.utc))
            resolved=[p for p in third["packages"]["items"] if p.get("lifecycle") == "resolved"]
            self.assertEqual(sorted(p["package_id"] for p in resolved), sorted(package_ids))
            self.assertTrue(all(p.get("notify") for p in resolved))
            brief_resolved=[x for section in third["brief"]["items"] if section["section"] == "high_medium_packages" for x in section["items"]]
            self.assertEqual(sorted(p["package_id"] for p in brief_resolved), sorted(package_ids))


if __name__ == "__main__":
    unittest.main()
