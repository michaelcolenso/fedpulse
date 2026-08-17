import unittest

from fedpulse.canonical_text import canonical_event_text, canonical_profile_text


class CanonicalTextTests(unittest.TestCase):
    def test_sam_uses_place_of_performance_and_not_office_geography(self):
        item = {
            "source": "sam_opportunity",
            "kind": "contract_opportunity",
            "title": "Roof replacement",
            "agency": "VA",
            "stage": "Sources Sought",
            "payload": {"row": {
                "PopCity": "Tacoma", "PopState": "WA", "City": "Washington", "State": "DC",
                "NaicsCode": "238160", "Description": "Replace the facility roof.",
            }},
        }
        text = canonical_event_text(item)
        self.assertIn("Place of performance: Tacoma, WA", text)
        self.assertNotIn("Washington, DC", text)
        self.assertIn("NAICS: 238160", text)

    def test_grants_representation_contains_program_semantics(self):
        item = {
            "source": "grants_gov", "kind": "funding_opportunity", "title": "AI infrastructure hubs",
            "agency": "NSF", "stage": "Forecast",
            "payload": {"OpportunityNumber": "NSF-26-X", "EligibleApplicants": "Universities",
                        "EstimatedFunding": "100000000", "Description": "Regional AI compute infrastructure."},
        }
        text = canonical_event_text(item)
        self.assertIn("Opportunity number: NSF-26-X", text)
        self.assertIn("Eligibility: Universities", text)
        self.assertIn("Regional AI compute infrastructure", text)

    def test_profile_text_is_semantic_query_not_only_keywords(self):
        text = canonical_profile_text("aec", {"label": "Seattle construction", "keywords": ["roofing", "renovation"],
                                               "geographies": ["Seattle", "Tacoma"], "agencies": ["VA"],
                                               "naics": ["238160"]})
        self.assertIn("Watch profile: Seattle construction", text)
        self.assertIn("Geographies: Seattle, Tacoma", text)
        self.assertIn("NAICS: 238160", text)


if __name__ == "__main__":
    unittest.main()
