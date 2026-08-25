from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import sys
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import eml_pmw


class IntegrationPackagingTests(unittest.TestCase):
    def test_runtime_metadata_declares_jsonschema_and_profile_version(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]
        self.assertIn("jsonschema>=4.23,<5", project["dependencies"])
        self.assertEqual(project["version"], "0.3.0")
        self.assertEqual(eml_pmw.__version__, "0.3.0")

    def test_package_resources_include_profile_and_all_locked_schemas(self):
        root = files("eml_pmw.contracts")
        for name in (
            "participant-binding-v1.schema.json",
            "integration-profile-v1.schema.json",
            "integration-profile-v1.json",
            "conformance-bundle-v1.schema.json",
        ):
            self.assertTrue(root.joinpath(name).is_file(), name)
        locked = root.joinpath("mrmic_phase13")
        for name in (
            "lock.json",
            "mrmic-capabilities-v1.schema.json",
            "native-resource-portal-v1.schema.json",
            "secure-canvas-messages-v1.schema.json",
            "ephemeral-runtime-presence-v1.schema.json",
            "live-portal-host-v1.schema.json",
        ):
            self.assertTrue(locked.joinpath(name).is_file(), name)


if __name__ == "__main__":
    unittest.main()
