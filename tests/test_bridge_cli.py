from __future__ import annotations

from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_bridge.cli import _print


class CliOutputTests(unittest.TestCase):
    def test_json_output_falls_back_safely_on_cp950_console(self):
        raw = io.BytesIO()
        console = io.TextIOWrapper(raw, encoding="cp950", errors="strict", write_through=True)

        with redirect_stdout(console):
            _print({"text": "✻中文"})

        console.flush()
        decoded = raw.getvalue().decode("cp950")
        self.assertEqual(json.loads(decoded), {"text": "✻中文"})


if __name__ == "__main__":
    unittest.main()
