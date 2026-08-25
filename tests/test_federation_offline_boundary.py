from __future__ import annotations

from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from scripts.check_federation_offline_boundary import scan_offline_boundary


class FederationOfflineBoundaryTests(unittest.TestCase):
    def test_current_federation_package_has_no_live_effect_surface(self):
        self.assertEqual(scan_offline_boundary(ROOT / "src" / "eml_pmw" / "federation"), [])

    def test_injected_network_process_and_provider_surfaces_turn_gate_red(self):
        cases = {
            "socket.py": ("import socket\nsocket.create_connection(('example.test', 443))\n", "forbidden_import:socket"),
            "process.py": ("import subprocess\nsubprocess.run(['provider'])\n", "forbidden_import:subprocess"),
            "provider.py": ("from eml_wake.provider import ClaudeCLIAdapter\n", "forbidden_import:eml_wake.provider"),
            "url.py": ("from urllib.request import urlopen\nurlopen('https://example.test')\n", "forbidden_import:urllib.request"),
        }
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, (source, expected) in cases.items():
                path = root / name
                path.write_text(source, encoding="utf-8")
                with self.subTest(name=name):
                    findings = scan_offline_boundary(root)
                    self.assertIn(expected, [item.code for item in findings])
                path.unlink()


if __name__ == "__main__":
    unittest.main()
