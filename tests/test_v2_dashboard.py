import re
import unittest
from pathlib import Path

REPO=Path(__file__).parents[1]
ROOT=REPO/"dashboard"
REQUIRED_FEEDS=(
    "daily_activity.json",
    "packages.json",
    "standalone.json",
    "fr_metrics.json",
    "marc_horizon.json",
    "health.json",
    "brief.json",
    "opportunities_today.json",
    "hidden_gems.json",
)

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

    def test_every_reader_feed_is_published_served_and_verified(self):
        publisher=(REPO/"scripts/publish_dashboard.py").read_text()
        worker=(REPO/"worker/src/index.js").read_text()
        verifier=(REPO/"scripts/verify_live_dashboard.py").read_text()
        nightly=(REPO/".github/workflows/nightly.yml").read_text()
        for name in REQUIRED_FEEDS:
            stem=name.removesuffix(".json")
            self.assertIn(f'"{stem}"', publisher, f"publisher omits {name}")
            self.assertIn(f'"{name}"', worker, f"worker omits {name}")
            self.assertIn(f'"{name}"', verifier, f"live verifier omits {name}")
        self.assertIn("Verify every live dashboard feed", nightly)
        self.assertIn("verify_live_dashboard.py", nightly)

    def test_generation_fallback_never_masks_declared_missing_objects(self):
        worker=(REPO/"worker/src/index.js").read_text()
        self.assertIn("const declared", worker)
        self.assertIn("if (!declared)", worker)
        self.assertIn("incomplete_generation", worker)
        self.assertIn("legacy-fallback", worker)

if __name__ == "__main__": unittest.main()
