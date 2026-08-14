import unittest
from dataclasses import replace
from tests.v2_helpers import fr_record, load_case, temp_db, seed_records
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

    def test_new_package_id_uses_coordination_date_and_core_only(self):
        rows=self._enriched("ncua_package")
        identity=package_identity(rows)
        self.assertEqual(identity["package_id"],f"{identity['coordination_agency_id']}:{identity['earliest_publication_date']}:{identity['core_cluster_key']}")

    def test_evidence_change_creates_new_immutable_version(self):
        rows=self._enriched("ncua_package")
        with temp_db() as conn:
            seed_records(conn,load_case("ncua_package")); normalize_all(conn)
            first_package=score_package(rows)
            first=persist_package_versions(conn,[first_package],"2026-08-07T00:00:00Z")[0]
            revised=score_package([replace(rows[0],title="REVISED TITLE"),*rows[1:]],prior_state=first_package)
            second=persist_package_versions(conn,[revised],"2026-08-08T00:00:00Z")[0]
            self.assertNotEqual(first["package_version_id"],second["package_version_id"])
            self.assertEqual(second["supersedes_version_id"],first["package_version_id"])

    def test_count_alone_is_not_high_and_missing_url_downgrades(self):
        rows = self._enriched("unrelated_same_day_notices")
        forced = [replace(r, topics=("Shared",), direction="mixed_or_unknown", sectors=()) for r in rows]
        result = score_package(forced)
        self.assertNotEqual(result["confidence"], "high")
        good = self._enriched("ncua_package")
        result = score_package([replace(good[0], url=None), *good[1:]])
        self.assertNotEqual(result["confidence"], "high")

    def test_parent_coordination_is_explicit_and_taxonomy_versions_are_in_evidence(self):
        rows = self._enriched("cdc_funding_package")
        result = score_package(rows)
        self.assertIn(result["confidence"], {"high", "medium"})
        self.assertEqual(result["coordination_agency_id"], "cdc")
        self.assertTrue(result["taxonomy_versions"])
        self.assertTrue(all(e["metadata"]["taxonomy_versions"] == result["taxonomy_versions"] for e in result["evidence"]))

    def test_known_parent_allows_coherent_sibling_children_but_not_unrelated_parent(self):
        rows = self._enriched("cdc_funding_package")
        sibling = replace(rows[1], canonical_agency_id="fictional-child", canonical_agency_name="Fictional Child", parent_id="hhs")
        result = score_package([rows[0], sibling])
        self.assertIn(result["confidence"], {"high", "medium"})
        self.assertEqual(result["coordination_agency_id"], "hhs")
        unrelated = replace(rows[1], canonical_agency_id="fictional-child", canonical_agency_name="Fictional Child", parent_id="other-parent")
        self.assertEqual(bounded_components([rows[0], unrelated], candidate_edges([rows[0], unrelated])), [])

    def test_parent_coordination_allows_multiple_records_per_child(self):
        rows = self._enriched("cdc_funding_package")
        sibling = replace(rows[0], record_id="fr:hhs-sibling", canonical_agency_id="fictional-child", canonical_agency_name="Fictional Child", parent_id="hhs")
        result = score_package(rows + [sibling])
        self.assertEqual(result["coordination_agency_id"], "hhs")
        self.assertIn(result["confidence"], {"high", "medium"})

    def test_concurrent_same_agency_packages_do_not_reconcile_without_core_match(self):
        with temp_db() as conn:
            first = [fr_record(f"a-{i}", "National Credit Union Administration", "2026-08-01", title="Remove credit union burden", topics=["Credit unions"]) for i in range(3)]
            second = [fr_record(f"b-{i}", "National Credit Union Administration", "2026-08-01", title="Require cybersecurity controls", topics=["Cybersecurity"]) for i in range(3)]
            seed_records(conn, first); normalize_all(conn)
            initial = persist_package_versions(conn, detect_packages(conn, "2026-08-01"), "2026-08-01T12:00:00Z")
            seed_records(conn, second); normalize_all(conn)
            later = detect_packages(conn, "2026-08-01")
            self.assertEqual(len(later), 2)
            self.assertEqual(sum(p["package_id"] == initial[0]["package_id"] for p in later), 1)
            self.assertEqual(len({p["package_id"] for p in later}), 2)

    def test_detect_reconciles_added_member_against_persisted_package(self):
        with temp_db() as conn:
            original = load_case("ncua_package")
            seed_records(conn, original); normalize_all(conn)
            first = detect_packages(conn, "2026-08-06")
            persisted = persist_package_versions(conn, first, "2026-08-07T00:00:00Z")
            extra = dict(original[0]); extra["id"] = "fr:ncua-added"; extra["title"] = "Additional credit union action"
            seed_records(conn, [extra]); normalize_all(conn)
            second = detect_packages(conn, "2026-08-06")
            self.assertEqual(second[0]["package_id"], persisted[0]["package_id"])
            newer = persist_package_versions(conn, second, "2026-08-08T00:00:00Z")
            self.assertEqual(newer[0]["supersedes_version_id"], persisted[0]["package_version_id"])

if __name__ == "__main__": unittest.main()
