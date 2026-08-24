from __future__ import annotations

import json
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_handoff.models import HandoffConfig


class HandoffExampleTests(unittest.TestCase):
    def test_example_config_is_portable_and_contract_valid(self):
        path = ROOT / "examples" / "handoff" / "config.example.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        config = HandoffConfig.from_dict(value)
        self.assertEqual(config.allowed_target_kinds, ("shared_topic", "task"))
        for source_root in value["allowed_source_roots"]:
            self.assertIsNone(re.match(r"^[A-Za-z]:[\\/]", source_root))
            self.assertTrue(source_root.startswith("<SHARED_ROOT>/"))

    def test_example_payload_is_small_p1_markdown_without_secret_shape(self):
        path = ROOT / "examples" / "handoff" / "payload.example.md"
        data = path.read_bytes()
        self.assertGreater(len(data), 0)
        self.assertLessEqual(len(data), 1_048_576)
        text = data.decode("utf-8")
        self.assertNotRegex(text, r"(?i)(api[_-]?key|token|password)\s*[:=]")

    def test_readme_links_design_and_documents_provider_free_commands(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        relative = "docs/architecture/Local_Durable_Handoff_Mailbox_v0.1.md"
        self.assertTrue((ROOT / relative).is_file())
        self.assertIn(relative, readme)
        self.assertIn("eml-handoff", readme)
        self.assertIn("does not start a provider", " ".join(readme.split()))

    def test_roadmap_lists_only_local_mailbox_as_verified(self):
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
        self.assertIn("Local Durable Handoff Mailbox v0.1", roadmap)
        self.assertIn("ARCP–PMW–MRMIC Integration Profile v1", roadmap)


if __name__ == "__main__":
    unittest.main()
