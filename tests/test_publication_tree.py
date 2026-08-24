from __future__ import annotations

import io
import json
from pathlib import Path
import tempfile
import unittest

from scripts.check_publication_tree import check_publication_tree, main


class PublicationTreeGateTests(unittest.TestCase):
    def test_allowed_first_party_source_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "src" / "eml_wake" / "store.py"
            path.parent.mkdir(parents=True)
            path.write_text("def wake_key(value):\n    return value\n", encoding="utf-8")

            self.assertEqual(check_publication_tree(root, ["src/eml_wake/store.py"]), [])

    def test_forbidden_populations_are_rejected_by_path(self):
        cases = {
            "upstream/herdr/src/main.rs": "forbidden_path",
            "runtime/bridge/bridge.sqlite3": "forbidden_path",
            "recovery/checkpoint.zip": "forbidden_path",
            "build/lib/eml_wake/cli.py": "forbidden_path",
            "src/pkg.egg-info/PKG-INFO": "generated_path",
            "evidence/raw/session.jsonl": "forbidden_path",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for relative, expected in cases.items():
                with self.subTest(relative=relative):
                    findings = check_publication_tree(root, [relative])
                    self.assertEqual([item.code for item in findings], [expected])

    def test_manifest_rejects_absolute_and_parent_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            findings = check_publication_tree(root, ["../outside.txt", "C:/outside.txt"])
            self.assertEqual([item.code for item in findings], ["unsafe_manifest_path", "unsafe_manifest_path"])

    def test_machine_local_paths_are_reported_without_echoing_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "docs" / "bad.md"
            path.parent.mkdir(parents=True)
            slash = chr(92)
            path.write_text(
                f"one C:{slash}Users{slash}example{slash}private\n"
                f"two D:{slash}AI_RESIDENCE{slash}AI_HOME\n"
                "three D:/" + "Ai/work together/project\n",
                encoding="utf-8",
            )

            findings = check_publication_tree(root, ["docs/bad.md"])
            self.assertEqual([item.code for item in findings], ["local_path", "local_path", "local_path"])
            self.assertEqual([item.line for item in findings], [1, 2, 3])
            self.assertTrue(all("example" not in item.detail for item in findings))

    def test_credential_shaped_assignment_is_redacted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            path = root / "config.txt"
            key_name = "api" + "_key"
            secret_value = "public" + "ation-canary-value"
            path.write_text(f'{key_name} = "{secret_value}"\n', encoding="utf-8")

            findings = check_publication_tree(root, ["config.txt"])
            self.assertEqual([item.code for item in findings], ["credential_assignment"])
            self.assertEqual(findings[0].detail, "field=api_key")
            self.assertNotIn(secret_value, repr(findings[0]))

    def test_cli_emits_deterministic_json_and_nonzero_for_red_control(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "manifest.txt"
            manifest.write_text("runtime/bridge/bridge.sqlite3\n", encoding="utf-8")
            output = io.StringIO()

            code = main(["--root", str(root), "--manifest", str(manifest)], stdout=output)

            self.assertEqual(code, 2)
            self.assertEqual(
                json.loads(output.getvalue()),
                {
                    "findings": [
                        {
                            "code": "forbidden_path",
                            "detail": "top_level=runtime",
                            "line": None,
                            "path": "runtime/bridge/bridge.sqlite3",
                        }
                    ],
                    "passed": False,
                },
            )


if __name__ == "__main__":
    unittest.main()
