from __future__ import annotations

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WakeExampleTests(unittest.TestCase):
    def test_example_config_request_and_payload_are_mutually_consistent(self):
        from eml_wake.canonical import loads_strict
        from eml_wake.models import WakeConfig, WakeRequest

        example = ROOT / "examples" / "wake"
        config_file = example / "config.example.json"
        request_file = example / "generic-worker-request.example.json"
        payload_file = example / "payload.example.md"
        for path in (config_file, request_file, payload_file):
            self.assertTrue(path.is_file(), f"missing example: {path}")

        config = WakeConfig.from_dict(loads_strict(config_file.read_bytes()))
        request = WakeRequest.from_dict(loads_strict(request_file.read_bytes()))
        self.assertEqual(config.allowed_models, ("claude-haiku-4-5-20251001",))
        self.assertEqual(request.model, "claude-haiku-4-5-20251001")
        self.assertEqual(request.allowed_tools, ())
        self.assertEqual(request.target_kind, "generic_worker")
        self.assertEqual(request.payload_ref, "payload.example.md")
        self.assertEqual(
            request.payload_sha256,
            hashlib.sha256(payload_file.read_bytes()).hexdigest().upper(),
        )


if __name__ == "__main__":
    unittest.main()
