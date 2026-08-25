from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import jsonschema
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.integration.contracts import load_contract, verify_contract_lock


EXPECTED = {
    "mrmic-capabilities-v1.schema.json": "a51a8611926bbf322d75308cc17a7c80a6348cbb4629a89da2375d0a2071f73e",
    "native-resource-portal-v1.schema.json": "a6204a402d3fd971f6188c92c385b792da30f457142ff13cc3c69bc389cc6832",
    "secure-canvas-messages-v1.schema.json": "998f3bc1cc10563e1cec416451e427fd860ad07cc956ad0c923537985d14f54c",
    "ephemeral-runtime-presence-v1.schema.json": "5ff2932eb07b69ffb2e4a071017dab33d055eb7f97c6b6bc0bd8d3e31cf2ae5e",
    "live-portal-host-v1.schema.json": "1c9ddf86ae83eae039963fe8ae19ff0b33795f3a886423a99db0f9cd3482b7a6",
}


class ContractLockTests(unittest.TestCase):
    def test_exact_upstream_contracts_match_lock(self):
        result = verify_contract_lock()
        self.assertTrue(result.valid)
        self.assertEqual(
            result.source_commit, "791efb9d98270d4db9c25f257aac805196ba62e8"
        )
        self.assertEqual(result.digests, EXPECTED)

    def test_capabilities_schema_is_loaded_from_package_resources(self):
        schema = load_contract("mrmic-capabilities-v1.schema.json")
        self.assertEqual(
            schema["$id"],
            "https://evemisslab.com/schemas/mrmic-capabilities-v1.schema.json",
        )

    def test_all_locked_schemas_meta_validate(self):
        for name in EXPECTED:
            with self.subTest(name=name):
                jsonschema.Draft202012Validator.check_schema(load_contract(name))

    def test_one_byte_corruption_turns_the_gate_red(self):
        source = files("eml_pmw.contracts.mrmic_phase13")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for item in source.iterdir():
                if item.name.endswith(".json"):
                    (root / item.name).write_bytes(item.read_bytes())
            target = root / "native-resource-portal-v1.schema.json"
            target.write_bytes(target.read_bytes() + b"\n")
            result = verify_contract_lock(root)
            self.assertFalse(result.valid)
            self.assertIn("contract_digest_mismatch", result.reason_codes)


if __name__ == "__main__":
    unittest.main()
