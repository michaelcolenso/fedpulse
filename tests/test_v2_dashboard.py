import re
import unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]/"dashboard"
class TestDashboard(unittest.TestCase):
    def test_v2_fetches_and_evidence_first_contract(self):
        html=(ROOT/"index.html").read_text(); js=(ROOT/"app.js").read_text()
        for name in ("daily_activity","packages","standalone","fr_metrics","marc_horizon","health","brief"):
            self.assertIn(name+".json",js)
        self.assertIn("freshness",html); self.assertIn("daily",html); self.assertIn("packages",html)
        self.assertNotRegex(js,r"api\\.json|rcr\\.json|ter\\.json")
        for token in ("agency-filter","direction-filter","sector-filter","family-filter","confidence-filter","lifecycle-filter"):
            self.assertIn(token,html)
        self.assertIn("esc(",js); self.assertIn("target=\"_blank\"",js); self.assertIn("rel=\"noopener noreferrer\"",js)
        self.assertIn("low-confidence",js)
        self.assertIn("methodology", html)
        self.assertIn("safeUrl", js)
        self.assertIn("details", js)
        self.assertIn("source_freshness", js)
        self.assertIn("last_publication_date", js)
        self.assertNotIn("innerHTML = value", js)

if __name__ == "__main__": unittest.main()
