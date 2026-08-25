from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts.check_ral_federation_seam import main
from tests.test_federation_ral_adapter import manifest_value


def run_check(manifest_path, source_path):
    output = io.StringIO()
    with redirect_stdout(output):
        code = main(
            [
                "--manifest",
                str(manifest_path),
                "--source-schema",
                str(source_path),
            ]
        )
    return code, json.loads(output.getvalue())


class FederationCrossRepoTests(unittest.TestCase):
    def test_generic_pin_checker_distinguishes_unavailable_from_mismatch(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.schema.json"
            source.write_text('{"$id":"https://example.test/source-v1"}', encoding="utf-8")
            raw = source.read_bytes()
            manifest = manifest_value(
                source_schema_id="https://example.test/source-v1",
                source_schema_version="1",
                source_repository="https://example.test/repository",
                source_commit="a" * 40,
                source_schema_bytes=len(raw),
                source_schema_sha256=__import__("hashlib").sha256(raw).hexdigest(),
                source_manifest_digest="sha256:sedb-ral-json-nfc-codepoint-v1:" + "b" * 64,
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )

            unavailable = run_check(manifest_path, root / "missing.schema.json")
            self.assertEqual(unavailable[0], 4)
            self.assertEqual(unavailable[1]["status"], "ral_source_unavailable")

            source.write_text('{"$id":"https://example.test/changed"}', encoding="utf-8")
            mismatch = run_check(manifest_path, source)
            self.assertEqual(mismatch[0], 2)
            self.assertEqual(mismatch[1]["status"], "ral_source_mismatch")

    def test_generic_pin_checker_accepts_exact_bytes_and_id(self):
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.schema.json"
            source.write_text('{"$id":"https://example.test/source-v1"}', encoding="utf-8")
            raw = source.read_bytes()
            manifest = manifest_value(
                source_schema_id="https://example.test/source-v1",
                source_schema_version="1",
                source_repository="https://example.test/repository",
                source_commit="a" * 40,
                source_schema_bytes=len(raw),
                source_schema_sha256=__import__("hashlib").sha256(raw).hexdigest(),
                source_manifest_digest="sha256:sedb-ral-json-nfc-codepoint-v1:" + "b" * 64,
            )
            manifest_path = root / "manifest.json"
            manifest_path.write_text(
                json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                encoding="utf-8",
            )

            result = run_check(manifest_path, source)

            self.assertEqual(result[0], 0)
            self.assertEqual(result[1]["status"], "verified")
            self.assertEqual(result[1]["source_schema_sha256"], manifest["source_schema_sha256"])


if __name__ == "__main__":
    unittest.main()
