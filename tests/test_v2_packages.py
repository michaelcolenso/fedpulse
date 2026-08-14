import unittest
from dataclasses import replace
from tests.v2_helpers import load_case, temp_db, seed_records
from fedpulse.normalize_agencies import normalize_all
from fedpulse.packages import (bounded_components, candidate_edges, detect_packages, enrich_record, package_identity, persist_package_versions, score_package)

class TestPackages(unittest.TestCase):
    def _enriched(self, case):
        rows = load_case(case)
        with temp_db() as conn:
            seed_records(conn, rows); normalize_all(conn)
            return [enrich_record(r) for r in conn.execute("select * from records order by id").fetchall() if r["id"] in {x["id"] for x in rows}]

    def test_golden_packages_form_and_unrelated_do_not(self):
        for case in ("ncua_package", "phmsa_package", "cdc_funding_package"):
            rows = self._enriched(case)
            edges = candidate_edges(rows)
            comps = bounded_components(rows, edges)
            self.assertEqual(len(comps), 1, case)
            result = score_package(comps[0])
            self.assertIn(result["direction"], {"reduce_or_rescind", "increase_or_require", "fund_or_award"})
            self.assertIn(result["confidence"], {"high", "medium"})
            self.assertEqual(len(result["evidence"]), len(rows))
        rows = self._enriched("unrelated_same_day_notices")
        self.assertEqual(bounded_components(rows, candidate_edges(rows)), [])

    def test_two_record_requires_both_coherence_and_chain_is_bounded(self):
        rows = self._enriched("transitive_date_chain")
        comps = bounded_components(rows, candidate_edges(rows))
        self.assertTrue(comps)
        self.assertTrue(all((max(r.publication_date for r in c) - min(r.publication_date for r in c)).days <= 2 for c in comps))
        self.assertFalse(any(len(c) == 3 for c in comps))

    def test_ids_are_stable_and_membership_change_supersedes(self):
        rows = self._enriched("ncua_package")
        package = score_package(bounded_components(rows, candidate_edges(rows))[0])
        ident1 = package_identity(rows)
        ident2 = package_identity(list(reversed(rows)))
        self.assertEqual(ident1["package_id"], ident2["package_id"])
        self.assertEqual(package["package_id"], ident1["package_id"])
        with temp_db() as conn:
            seed_records(conn, load_case("ncua_package")); normalize_all(conn)
            first = persist_package_versions(conn, [package], "2026-08-07T00:00:00Z")[0]
            again = persist_package_versions(conn, [package], "2026-08-07T01:00:00Z")[0]
            self.assertEqual(first["package_version_id"], again["package_version_id"])
            grown = score_package(rows + [replace(rows[0], record_id="fr:extra", title="Extra credit union action")])
            grown["package_id"] = package["package_id"]
            newer = persist_package_versions(conn, [grown], "2026-08-08T00:00:00Z")[0]
            self.assertNotEqual(first["package_version_id"], newer["package_version_id"])
            self.assertEqual(newer["supersedes_version_id"], first["package_version_id"])

    def test_count_alone_is_not_high_and_missing_url_downgrades(self):
        rows = self._enriched("unrelated_same_day_notices")
        forced = [replace(r, topics=("Shared",), direction="mixed_or_unknown", sectors=()) for r in rows]
        result = score_package(forced)
        self.assertNotEqual(result["confidence"], "high")
        good = self._enriched("ncua_package")
        result = score_package([replace(good[0], url=None), *good[1:]])
        self.assertNotEqual(result["confidence"], "high")

if __name__ == "__main__": unittest.main()
