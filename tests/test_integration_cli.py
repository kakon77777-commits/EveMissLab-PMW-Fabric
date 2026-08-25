from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_pmw.cli import main


POSITIVE = ROOT / "examples" / "integration" / "profile-v1-positive.json"
REJECTED = ROOT / "examples" / "integration" / "profile-v1-runtime-tag-negative.json"
INCOMPATIBLE = ROOT / "examples" / "integration" / "profile-v1-capability-negative.json"


def run_cli(path: Path):
    stream = io.StringIO()
    with redirect_stdout(stream):
        code = main(["profile-validate", str(path)])
    return code, json.loads(stream.getvalue()), stream.getvalue().encode("utf-8")


class ProfileCliTests(unittest.TestCase):
    def test_profile_validate_exit_codes_are_distinct(self):
        self.assertEqual(run_cli(POSITIVE)[0], 0)
        self.assertEqual(run_cli(REJECTED)[0], 2)
        self.assertEqual(run_cli(INCOMPATIBLE)[0], 3)

    def test_positive_output_is_byte_deterministic(self):
        first = run_cli(POSITIVE)
        second = run_cli(POSITIVE)
        self.assertEqual(first[0], 0)
        self.assertEqual(first[2], second[2])

    def test_unreadable_malformed_and_duplicate_inputs_are_typed_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            missing = root / "missing.json"
            malformed = root / "malformed.json"
            malformed.write_text("{not-json", encoding="utf-8")
            duplicate = root / "duplicate.json"
            duplicate.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
            self.assertEqual(run_cli(missing)[:2], (1, {"profile": "pmw-arcp-mrmic/v1", "status": "error", "reason_codes": ["input_unreadable"]}))
            self.assertEqual(run_cli(malformed)[:2], (1, {"profile": "pmw-arcp-mrmic/v1", "status": "error", "reason_codes": ["input_invalid_json"]}))
            self.assertEqual(run_cli(duplicate)[:2], (1, {"profile": "pmw-arcp-mrmic/v1", "status": "error", "reason_codes": ["input_duplicate_key"]}))


if __name__ == "__main__":
    unittest.main()
