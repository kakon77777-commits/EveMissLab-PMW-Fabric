from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.integration.bundle import validate_bundle


def load_example(name: str):
    return json.loads(
        (ROOT / "examples" / "integration" / name).read_text(encoding="utf-8")
    )


class BundleTests(unittest.TestCase):
    def test_positive_bundle_is_compatible(self):
        result = validate_bundle(load_example("profile-v1-positive.json"))
        self.assertEqual(result.status, "compatible")
        self.assertEqual(result.reason_codes, ())

    def test_runtime_tag_bundle_is_rejected(self):
        result = validate_bundle(
            load_example("profile-v1-runtime-tag-negative.json")
        )
        self.assertEqual(result.status, "rejected")
        self.assertIn("forbidden_entity_identifier_kind", result.reason_codes)

    def test_capability_negative_is_incompatible(self):
        result = validate_bundle(
            load_example("profile-v1-capability-negative.json")
        )
        self.assertEqual(result.status, "incompatible")
        self.assertIn("required_auth_mode_missing", result.reason_codes)

    def test_unmeasured_capability_is_not_rejection_or_false(self):
        value = load_example("profile-v1-positive.json")
        value["mrmicCapabilities"] = None
        result = validate_bundle(value)
        self.assertEqual(result.status, "unmeasured")
        self.assertIn("capability_document_unmeasured", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
