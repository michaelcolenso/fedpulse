import json
import tempfile
import unittest
from pathlib import Path
from fedpulse.digest import load_brief

class TestV2Digest(unittest.TestCase):
    def test_reads_schema_v2_and_rejects_legacy(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"brief.json"; p.write_text(json.dumps({"schema_version":2,"items":[]})); self.assertEqual(load_brief(p)["schema_version"],2)
            p.write_text(json.dumps({"agencies":[]}))
            with self.assertRaises(RuntimeError): load_brief(p)

if __name__ == "__main__": unittest.main()
