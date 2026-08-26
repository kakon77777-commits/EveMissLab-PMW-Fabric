from __future__ import annotations

from importlib.resources import files
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
import zipfile

import eml_pmw


ROOT = Path(__file__).resolve().parents[1]
RELATION_CONTRACT_SCHEMAS = (
    "activation-policy-v1.schema.json",
    "authority-candidate-v1.schema.json",
    "authority-evaluation-receipt-v1.schema.json",
    "commitment-v1.schema.json",
    "contract-version-v1.schema.json",
    "exit-path-v1.schema.json",
    "grant-authority-evidence-v1.schema.json",
    "normalized-instant-evidence-v1.schema.json",
    "party-acceptance-v1.schema.json",
    "party-evidence-pin-v1.schema.json",
    "relation-contract-event-v1.schema.json",
    "relation-contract-projection-v1.schema.json",
    "relation-version-v1.schema.json",
    "representation-grant-v1.schema.json",
    "survival-clause-v1.schema.json",
    "termination-terms-v1.schema.json",
)


class RelationContractPackagingTests(unittest.TestCase):
    def test_current_project_and_package_version_are_0_4_0(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]
        self.assertEqual(project["version"], "0.4.0")
        self.assertEqual(eml_pmw.__version__, "0.4.0")

    def test_installed_resources_include_every_relation_contract_schema(self):
        root = files("eml_pmw.contracts").joinpath("relation_contract")
        for name in RELATION_CONTRACT_SCHEMAS:
            with self.subTest(name=name):
                self.assertTrue(root.joinpath(name).is_file(), name)

    def test_clean_wheel_contains_profile_modules_schemas_and_cli(self):
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
            wheel = next(Path(temporary).glob("*.whl"))
            with zipfile.ZipFile(wheel) as archive:
                names = set(archive.namelist())
                for module in (
                    "activation.py",
                    "arcp_adapter.py",
                    "authority.py",
                    "cli.py",
                    "events.py",
                    "federation_adapter.py",
                    "portability.py",
                    "projector.py",
                    "ral_adapter.py",
                    "reducer.py",
                    "store.py",
                ):
                    self.assertIn(f"eml_pmw/relations/{module}", names)
                for schema in RELATION_CONTRACT_SCHEMAS:
                    self.assertIn(
                        f"eml_pmw/contracts/relation_contract/{schema}", names
                    )
                entry_points = next(
                    name for name in names if name.endswith(".dist-info/entry_points.txt")
                )
                entrypoint_text = archive.read(entry_points).decode("utf-8")
            self.assertIn("eml-pmw = eml_pmw.cli:main", entrypoint_text)


if __name__ == "__main__":
    unittest.main()
