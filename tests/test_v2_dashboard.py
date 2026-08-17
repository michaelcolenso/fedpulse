import re
import unittest
from pathlib import Path

ROOT=Path(__file__).parents[1]/"dashboard"
class TestDashboard(unittest.TestCase):
    def test_v2_fetches_and_evidence_first_contract(self):
        html=(ROOT/"index.html").read_text(); js=(ROOT/"app.js").read_text(); opportunities=(ROOT/"opportunities.js").read_text()
        for name in ("daily_activity","packages","standalone","fr_metrics","marc_horizon","health","brief"):
            self.assertIn(name,js)
        self.assertIn("${name}.json",js)
        for token in ("freshness","signals","daily-total","packages","fr-metrics"):
            self.assertIn(token,html)
        self.assertNotRegex(js,r"api\\.json|rcr\\.json|ter\\.json")
        for token in ("agency-filter","direction-filter","sector-filter","confidence-filter","lifecycle-filter"):
            self.assertIn(token,html)
        for token in ("What happened","Why it matters","Why FedPulse noticed","What to do","See the evidence"):
            self.assertIn(token,js)
        self.assertIn("Nothing requires your attention today",js)
        self.assertIn("<h2>Watch</h2>",html)
        self.assertIn("Evidence explorer",html)
        self.assertIn("ranking-mode",html)
        self.assertIn("evidence_summary",opportunities)
        self.assertIn("related_actions",opportunities)
        self.assertIn("FedPulse analysis",opportunities)
        self.assertIn("No generative model influenced",opportunities)
        self.assertIn("esc(",js); self.assertIn("target=\"_blank\"",js); self.assertIn("rel=\"noopener noreferrer\"",js)
        self.assertIn("low-confidence",js)
        self.assertIn("methodology", html.lower())
        self.assertIn("safeUrl", js)
        self.assertIn("details", js)
        self.assertIn("source_freshness", js)
        self.assertIn("x-fedpulse-generation", js)
        self.assertIn("mixed dashboard generations", js)
        self.assertNotIn("innerHTML = value", js)

if __name__ == "__main__": unittest.main()