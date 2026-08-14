import unittest
from tests.v2_helpers import load_case

from fedpulse.taxonomy import canonicalize_agency, classify_direction, coverage_tags, normalize_org, watchlist_matches

class TestTaxonomy(unittest.TestCase):
    def test_normalized_cdc_alias_and_unknown(self):
        self.assertEqual(normalize_org(" Centers for Disease Control and Prevention (U.S.) "), normalize_org("Centers for Disease Control and Prevention"))
        a = canonicalize_agency("marc", "Centers for Disease Control and Prevention (U.S.)")
        self.assertEqual(a.canonical_id, "cdc")
        self.assertEqual(a.mapping_method, "normalized_exact")
        self.assertIsNone(canonicalize_agency("marc", "Unreviewed Office").canonical_id)

    def test_direction_negation_boundary_and_phrase_precedence(self):
        negated = classify_direction(load_case("negated_direction")[0])
        self.assertEqual(negated["direction"], "mixed_or_unknown")
        self.assertFalse(any(p["direction"] == "reduce_or_rescind" for p in negated["matched_phrases"]))
        reduced = classify_direction({"action": "The Board is rescinding redundant requirements."})
        self.assertEqual(reduced["direction"], "reduce_or_rescind")
        self.assertTrue(reduced["matched_phrases"])
        self.assertEqual(reduced["direction_dictionary_version"], "direction-v1")
        self.assertEqual(classify_direction({"abstract": "A mandate is required."})["direction"], "increase_or_require")
        self.assertEqual(classify_direction({"abstract": "removeable widgets"})["direction"], "mixed_or_unknown")

    def test_coverage_provenance_and_watchlist_exact_rule(self):
        row = load_case("nist_standalone")[0]
        identity = canonicalize_agency("fr", row["agency"])
        tags = coverage_tags(row, identity)
        self.assertTrue(any(t["sector"] == "cybersecurity" and t["source"] == "exact_fr_topic" for t in tags))
        matches = watchlist_matches(row, identity)
        self.assertTrue(matches)
        self.assertTrue(all(m["rule"] and m["watchlist"] for m in matches))
        self.assertFalse(watchlist_matches({"title":"cybersecurity-ishx", "subjects":[]}, identity))

if __name__ == "__main__": unittest.main()
