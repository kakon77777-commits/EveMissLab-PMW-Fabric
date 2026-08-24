from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

from tests.test_wake_contracts import valid_config


ROOT = Path(__file__).resolve().parents[1]


def powershell_executable() -> str:
    configured = os.environ.get("EML_WAKE_TEST_POWERSHELL")
    value = configured or shutil.which("pwsh") or shutil.which("powershell")
    if not value:
        raise unittest.SkipTest("neither pwsh nor Windows PowerShell is available")
    return value


class WakePowerShellTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="eml wake ")
        self.base = Path(self.tmp.name)
        self.wake_root = self.base / "wake"
        self.config = self.base / "config.json"
        raw = valid_config()
        raw["allowed_payload_roots"] = [str(self.base)]
        raw["claude_binary"] = sys.executable
        self.config.write_text(json.dumps(raw), encoding="utf-8")
        self.pid = self.base / "watchdog.pid.json"

    def tearDown(self):
        self.tmp.cleanup()

    def run_script(self, name: str, *extra):
        script = ROOT / "scripts" / name
        if not script.is_file():
            self.fail(f"PowerShell launcher not implemented: {script}")
        proc = subprocess.run(
            [
                powershell_executable(),
                "-NoProfile",
                "-File",
                str(script),
                "-PackageRoot",
                str(ROOT),
                "-ConfigPath",
                str(self.config),
                "-WakeRoot",
                str(self.wake_root),
                "-PidPath",
                str(self.pid),
                *extra,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        return proc, json.loads(proc.stdout)

    def test_start_validate_only_reports_hidden_exact_command_without_starting(self):
        proc, value = self.run_script("Start-EmlWakeWatchdog.ps1", "-ValidateOnly")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(value["status"], "ready")
        self.assertEqual(value["window_style"], "Hidden")
        self.assertEqual(value["module"], "eml_wake")
        self.assertEqual(Path(value["config_path"]), self.config.resolve())
        self.assertEqual(Path(value["wake_root"]), self.wake_root.resolve())
        self.assertFalse(self.pid.exists())

    def test_start_validate_only_rejects_missing_config(self):
        self.config.unlink()
        proc, value = self.run_script("Start-EmlWakeWatchdog.ps1", "-ValidateOnly")
        self.assertEqual(proc.returncode, 2)
        self.assertEqual(value["error"]["code"], "config_missing")
        self.assertFalse(self.pid.exists())

    def test_stop_validate_only_reports_not_running_without_killing(self):
        proc, value = self.run_script("Stop-EmlWakeWatchdog.ps1", "-ValidateOnly")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(value["status"], "not_running")
        self.assertFalse(self.pid.exists())

    def test_start_and_stop_lifecycle_survives_paths_with_spaces(self):
        if os.name != "nt":
            self.skipTest("the hidden-window watchdog launcher is Windows-specific")
        start = ROOT / "scripts" / "Start-EmlWakeWatchdog.ps1"
        stop = ROOT / "scripts" / "Stop-EmlWakeWatchdog.ps1"
        common = [
            "-PackageRoot",
            str(ROOT),
            "-ConfigPath",
            str(self.config),
            "-WakeRoot",
            str(self.wake_root),
            "-PidPath",
            str(self.pid),
        ]
        started_pid = None
        try:
            start_proc = subprocess.run(
                [powershell_executable(), "-NoProfile", "-File", str(start), *common],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            start_value = json.loads(start_proc.stdout)
            self.assertEqual(start_proc.returncode, 0, start_proc.stderr)
            self.assertEqual(start_value["status"], "started")
            started_pid = int(start_value["pid"])
            time.sleep(0.8)
            probe = subprocess.run(
                [
                    powershell_executable(),
                    "-NoProfile",
                    "-Command",
                    f"if (Get-Process -Id {started_pid} -ErrorAction SilentlyContinue) {{ exit 0 }} else {{ exit 1 }}",
                ],
                check=False,
            )
            self.assertEqual(probe.returncode, 0, "watchdog exited immediately")

            stop_proc = subprocess.run(
                [powershell_executable(), "-NoProfile", "-File", str(stop), *common],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            stop_value = json.loads(stop_proc.stdout)
            self.assertEqual(stop_proc.returncode, 0, stop_proc.stderr)
            self.assertEqual(stop_value["status"], "stopped")
            self.assertFalse(self.pid.exists())
            started_pid = None
        finally:
            if started_pid is not None:
                subprocess.run(
                    [powershell_executable(), "-NoProfile", "-Command", f"Stop-Process -Id {started_pid} -ErrorAction SilentlyContinue"],
                    check=False,
                )

    def test_live_probe_validate_only_reports_exact_inputs_without_running_provider(self):
        script = ROOT / "scripts" / "Test-EmlWakeLive.ps1"
        if not script.is_file():
            self.fail(f"PowerShell live probe not implemented: {script}")
        proc = subprocess.run(
            [
                powershell_executable(),
                "-NoProfile",
                "-File",
                str(script),
                "-PackageRoot",
                str(ROOT),
                "-LiveRoot",
                str(self.base),
                "-ClaudeBinary",
                powershell_executable(),
                "-ValidateOnly",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if not proc.stdout.strip():
            self.fail(f"live probe validate-only produced no JSON: {proc.stderr}")
        value = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(value["status"], "ready")
        self.assertEqual(Path(value["package_root"]), ROOT.resolve())
        self.assertEqual(Path(value["live_root"]), self.base.resolve())
        self.assertFalse(value["provider_invoked"])

    def test_live_probe_validate_only_accepts_default_bare_claude(self):
        if shutil.which("claude") is None:
            self.skipTest("default Claude command is not installed in this environment")
        script = ROOT / "scripts" / "Test-EmlWakeLive.ps1"
        proc = subprocess.run(
            [
                powershell_executable(),
                "-NoProfile",
                "-File",
                str(script),
                "-PackageRoot",
                str(ROOT),
                "-LiveRoot",
                str(self.base),
                "-ValidateOnly",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if not proc.stdout.strip():
            self.fail(f"live probe did not accept the default Claude binary: {proc.stderr}")
        value = json.loads(proc.stdout)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(value["status"], "ready")
        self.assertEqual(value["claude_binary"], "claude")
        self.assertFalse(value["provider_invoked"])

    def test_live_probe_wrapper_does_not_claim_provider_invocation_on_inner_failure(self):
        script = ROOT / "scripts" / "Test-EmlWakeLive.ps1"
        powershell = powershell_executable()
        proc = subprocess.run(
            [
                powershell_executable(),
                "-NoProfile",
                "-File",
                str(script),
                "-PackageRoot",
                str(ROOT),
                "-Python",
                powershell,
                "-LiveRoot",
                str(self.base),
                "-ClaudeBinary",
                powershell,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        value = json.loads(proc.stdout.strip().splitlines()[-1])
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(value["error"]["code"], "live_probe_failed")
        self.assertTrue(value.get("live_test_invoked"))
        self.assertEqual(value.get("provider_invocation_status"), "unmeasured")
        self.assertNotIn("provider_invoked", value)


if __name__ == "__main__":
    unittest.main()
