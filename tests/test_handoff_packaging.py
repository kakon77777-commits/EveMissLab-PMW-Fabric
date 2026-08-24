from __future__ import annotations

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


class HandoffPackagingTests(unittest.TestCase):
    def test_pyproject_registers_handoff_console_script(self):
        project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
            "project"
        ]
        self.assertEqual(project["scripts"]["eml-handoff"], "eml_handoff.cli:entrypoint")

    def test_clean_wheel_contains_handoff_package_and_entrypoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            builder = os.environ.get("EML_BUILD_PYTHON") or shutil.which("python") or sys.executable
            subprocess.run(
                [
                    builder,
                    "-m",
                    "build",
                    "--wheel",
                    "--no-isolation",
                    "--outdir",
                    tmp,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            wheels = list(Path(tmp).glob("*.whl"))
            self.assertEqual(len(wheels), 1)
            with zipfile.ZipFile(wheels[0]) as archive:
                names = set(archive.namelist())
                self.assertIn("eml_handoff/cli.py", names)
                entry_points = next(
                    name for name in names if name.endswith(".dist-info/entry_points.txt")
                )
                text = archive.read(entry_points).decode("utf-8")
            self.assertIn("eml-handoff = eml_handoff.cli:entrypoint", text)


if __name__ == "__main__":
    unittest.main()
