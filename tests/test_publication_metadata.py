from __future__ import annotations

import json
from pathlib import Path
import re
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]


def _all_strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value:
            yield from _all_strings(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _all_strings(item)


class PublicationMetadataTests(unittest.TestCase):
    def test_apache_license_and_package_metadata_agree(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]

        self.assertIn("Apache License", license_text)
        self.assertIn("Version 2.0, January 2004", license_text)
        self.assertIn("http://www.apache.org/licenses/", license_text)
        self.assertEqual(project["license"], "Apache-2.0")

    def test_roadmap_separates_verified_and_future_horizons(self):
        roadmap = (ROOT / "ROADMAP.md").read_text(encoding="utf-8")
        for heading in (
            "Verified foundation",
            "Canvas integration",
            "Shared collaboration",
            "Advanced shared world",
        ):
            self.assertIn(heading, roadmap)
        self.assertIn("Roadmap entries are non-claims", roadmap)

    def test_capability_example_is_portable_and_preserves_nonclaims(self):
        capability = json.loads((ROOT / "CAPABILITY.example.json").read_text(encoding="utf-8"))
        values = list(_all_strings(capability))

        self.assertEqual(capability["classification"], "portable_example")
        self.assertEqual(capability["entrypoints"]["wake_source"], "src/eml_wake")
        self.assertIn("exact_interactive_instance_wake", capability["not_proven"])
        self.assertIn("resident_identity_continuity", capability["not_proven"])
        local_pattern = re.compile(
            r"(?:^[A-Za-z]:[\\/]" + "|C:/" + "Users|D:/" + "AI_RESIDENCE)"
        )
        self.assertTrue(all(not local_pattern.search(item) for item in values))

    def test_public_release_evidence_contains_no_machine_runtime_fields(self):
        path = ROOT / "evidence" / "release" / "2026-08-24-validation.json"
        evidence = json.loads(path.read_text(encoding="utf-8"))
        encoded = json.dumps(evidence, ensure_ascii=False, sort_keys=True)

        self.assertGreaterEqual(evidence["source_tests"]["passed"], 123)
        self.assertEqual(evidence["source_tests"]["failed"], 0)
        self.assertGreaterEqual(evidence["source_tests"]["skipped"], 1)
        self.assertEqual(evidence["review"]["verdict"], "FINAL ACCEPT")
        for forbidden in (
            "pid",
            "provider_session_id",
            "payload",
            "transcript",
            "C:" + chr(92) * 2 + "Users",
            "D:/" + "Ai",
        ):
            self.assertNotIn(forbidden, encoded)

    def test_public_ci_is_offline_and_runs_deterministic_gates(self):
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("python -m unittest discover -s tests", workflow)
        self.assertIn("python -m compileall -q src", workflow)
        self.assertIn("python -m build --wheel", workflow)
        self.assertNotIn("EML_WAKE_LIVE", workflow)
        self.assertNotIn("secrets.", workflow)

    def test_public_docs_and_readme_are_linked(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        required = (
            "ROADMAP.md",
            "docs/architecture/Canvas_First_Integration_Contract_v0.1.md",
            "docs/security/SECURITY_BOUNDARIES.md",
            "docs/operations/WAKE_QUICKSTART.md",
        )
        for relative in required:
            self.assertTrue((ROOT / relative).is_file(), relative)
            self.assertIn(relative, readme)


if __name__ == "__main__":
    unittest.main()
