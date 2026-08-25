from __future__ import annotations

from importlib.resources import files
from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import eml_pmw


FEDERATION_SCHEMAS = (
    "adapter-visibility-evidence-v1.schema.json",
    "federated-event-v1.schema.json",
    "federation-config-v1.schema.json",
    "federation-inventory-v1.schema.json",
    "ral-public-projection-adapter-v1.schema.json",
    "receiver-adoption-receipt-v1.schema.json",
)


class FederationPackagingTests(unittest.TestCase):
    def test_version_and_package_resources_publish_complete_profile(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]
        self.assertEqual(project["version"], "0.3.0")
        self.assertEqual(eml_pmw.__version__, "0.3.0")
        contracts = files("eml_pmw.contracts")
        for name in FEDERATION_SCHEMAS:
            with self.subTest(name=name):
                self.assertTrue(contracts.joinpath(name).is_file(), name)

    def test_clean_wheel_contains_federation_modules_contracts_and_cli(self):
        with tempfile.TemporaryDirectory() as temporary:
            builder = (
                os.environ.get("EML_BUILD_PYTHON")
                or shutil.which("python")
                or sys.executable
            )
            subprocess.run(
                [
                    builder,
                    "-m",
                    "build",
                    "--wheel",
                    "--no-isolation",
                    "--outdir",
                    temporary,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            wheels = list(Path(temporary).glob("*.whl"))
            self.assertEqual(len(wheels), 1)
            with zipfile.ZipFile(wheels[0]) as archive:
                names = set(archive.namelist())
                for module in (
                    "authority.py",
                    "causal.py",
                    "cli.py",
                    "importer.py",
                    "inventory.py",
                    "projector.py",
                    "reconcile.py",
                    "store.py",
                    "visibility.py",
                ):
                    self.assertIn(f"eml_pmw/federation/{module}", names)
                for schema in FEDERATION_SCHEMAS:
                    self.assertIn(f"eml_pmw/contracts/{schema}", names)
                entry_points = next(
                    name for name in names if name.endswith(".dist-info/entry_points.txt")
                )
                entrypoint_text = archive.read(entry_points).decode("utf-8")
            self.assertIn("eml-pmw = eml_pmw.cli:main", entrypoint_text)


if __name__ == "__main__":
    unittest.main()
