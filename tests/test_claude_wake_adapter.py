from __future__ import annotations

import json
import subprocess
from unittest import mock
import unittest

from tests.test_wake_contracts import valid_request


def adapter_api():
    try:
        from eml_wake.claude import ClaudeCLIAdapter
        from eml_wake.errors import WakeError
        from eml_wake.models import WakeRequest
    except ModuleNotFoundError as exc:
        raise AssertionError("fresh Claude CLI wake adapter is not implemented") from exc
    return ClaudeCLIAdapter, WakeError, WakeRequest


def request(**changes):
    _, _, WakeRequest = adapter_api()
    raw = valid_request()
    raw.update(changes)
    return WakeRequest.from_dict(raw)


def success_payload(**changes) -> dict:
    value = {
        "is_error": False,
        "subtype": "success",
        "session_id": "11111111-2222-4333-8444-555555555555",
        "result": "WAKE_OK",
        "total_cost_usd": 0.0277,
        "duration_ms": 1234,
        "num_turns": 1,
        "stop_reason": "end_turn",
        "permission_denials": [],
        "api_error_status": None,
    }
    value.update(changes)
    return value


class RecordingRunner:
    def __init__(self, completed):
        self.completed = completed
        self.calls = []

    def __call__(self, argv, **kwargs):
        self.calls.append((list(argv), dict(kwargs)))
        if isinstance(self.completed, Exception):
            raise self.completed
        return self.completed


class ClaudeCLIAdapterTests(unittest.TestCase):
    def test_bare_binary_is_resolved_before_shell_false_launch(self):
        ClaudeCLIAdapter, _, _ = adapter_api()
        completed = subprocess.CompletedProcess(
            ["C:/resolved/claude.CMD"], 0, stdout=json.dumps(success_payload()), stderr=""
        )
        runner = RecordingRunner(completed)
        try:
            adapter = ClaudeCLIAdapter(
                binary="claude",
                runner=runner,
                resolver=lambda value: "C:/resolved/claude.CMD" if value == "claude" else None,
            )
        except TypeError as exc:
            self.fail(f"binary resolver injection is not implemented: {exc}")
        adapter.invoke(request(), "PAYLOAD")
        argv, _ = runner.calls[0]
        self.assertEqual(argv[0], "C:/resolved/claude.CMD")

    def test_uses_argv_stdin_explicit_model_and_empty_tools_without_resume(self):
        ClaudeCLIAdapter, _, _ = adapter_api()
        completed = subprocess.CompletedProcess(
            ["claude"], 0, stdout=json.dumps(success_payload()), stderr=""
        )
        runner = RecordingRunner(completed)
        adapter = ClaudeCLIAdapter(binary="claude", runner=runner)
        req = request()

        result = adapter.invoke(req, "PAYLOAD")

        argv, kwargs = runner.calls[0]
        self.assertEqual(argv[0], "claude")
        self.assertIn("-p", argv)
        self.assertIn("--safe-mode", argv)
        self.assertEqual(argv[argv.index("--output-format") + 1], "json")
        self.assertEqual(argv[argv.index("--model") + 1], req.model)
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "")
        self.assertEqual(argv[argv.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(argv[argv.index("--max-budget-usd") + 1], "0.1")
        self.assertIn("--append-system-prompt", argv)
        system_prompt = argv[argv.index("--append-system-prompt") + 1]
        self.assertIn("MODEL != RESIDENT", system_prompt)
        self.assertIn("fresh provider worker", system_prompt)
        self.assertNotIn("--resume", argv)
        self.assertNotIn("--fork-session", argv)
        self.assertNotIn("--fallback-model", argv)
        self.assertFalse(kwargs["shell"])
        self.assertEqual(kwargs["input"], "PAYLOAD")
        self.assertEqual(result.provider_session_id, success_payload()["session_id"])

    def test_allowed_tools_are_passed_as_one_comma_separated_argument(self):
        ClaudeCLIAdapter, _, _ = adapter_api()
        completed = subprocess.CompletedProcess(
            ["claude"], 0, stdout=json.dumps(success_payload()), stderr=""
        )
        runner = RecordingRunner(completed)
        adapter = ClaudeCLIAdapter(binary="claude", runner=runner)
        req = request(allowed_tools=["Read", "Bash"])
        adapter.invoke(req, "payload")
        argv, _ = runner.calls[0]
        self.assertEqual(argv[argv.index("--allowedTools") + 1], "Read,Bash")

    def test_success_output_maps_host_observed_fields_and_exact_cost(self):
        ClaudeCLIAdapter, _, _ = adapter_api()
        completed = subprocess.CompletedProcess(
            ["claude"], 0, stdout=json.dumps(success_payload()), stderr=""
        )
        result = ClaudeCLIAdapter(runner=RecordingRunner(completed)).invoke(request(), "payload")
        self.assertEqual(result.provider, "claude")
        self.assertEqual(result.model, "claude-haiku-4-5-20251001")
        self.assertEqual(result.provider_session_id, "11111111-2222-4333-8444-555555555555")
        self.assertEqual(result.result_text, "WAKE_OK")
        self.assertEqual(result.cost_microusd, 27700)
        self.assertEqual(result.duration_ms, 1234)
        self.assertRegex(result.watchdog_invocation_id, r"^invocation:")

    def test_malformed_or_incomplete_json_is_rejected(self):
        ClaudeCLIAdapter, WakeError, _ = adapter_api()
        outputs = ["not json", json.dumps({"is_error": False, "result": "x"})]
        for output in outputs:
            with self.subTest(output=output), self.assertRaises(WakeError) as caught:
                completed = subprocess.CompletedProcess(["claude"], 0, stdout=output, stderr="")
                ClaudeCLIAdapter(runner=RecordingRunner(completed)).invoke(request(), "payload")
            self.assertEqual(caught.exception.code, "provider_output_invalid")

    def test_nonzero_busy_and_generic_failure_are_distinct(self):
        ClaudeCLIAdapter, WakeError, _ = adapter_api()
        populations = [
            (subprocess.CompletedProcess(["claude"], 1, stdout="", stderr="Service is busy"), "provider_busy"),
            (subprocess.CompletedProcess(["claude"], 2, stdout="", stderr="bad argument"), "provider_failed"),
        ]
        for completed, code in populations:
            with self.subTest(code=code), self.assertRaises(WakeError) as caught:
                ClaudeCLIAdapter(runner=RecordingRunner(completed)).invoke(request(), "payload")
            self.assertEqual(caught.exception.code, code)

    def test_json_error_529_is_busy_and_other_json_error_is_failed(self):
        ClaudeCLIAdapter, WakeError, _ = adapter_api()
        populations = [
            (success_payload(is_error=True, api_error_status=529), "provider_busy"),
            (success_payload(is_error=True, api_error_status=500), "provider_failed"),
        ]
        for payload, code in populations:
            with self.subTest(code=code), self.assertRaises(WakeError) as caught:
                completed = subprocess.CompletedProcess(["claude"], 0, stdout=json.dumps(payload), stderr="")
                ClaudeCLIAdapter(runner=RecordingRunner(completed)).invoke(request(), "payload")
            self.assertEqual(caught.exception.code, code)

    def test_permission_denial_is_not_a_success(self):
        ClaudeCLIAdapter, WakeError, _ = adapter_api()
        payload = success_payload(permission_denials=["Read denied"])
        completed = subprocess.CompletedProcess(["claude"], 0, stdout=json.dumps(payload), stderr="")
        with self.assertRaises(WakeError) as caught:
            ClaudeCLIAdapter(runner=RecordingRunner(completed)).invoke(request(), "payload")
        self.assertEqual(caught.exception.code, "provider_permission_denied")

    def test_timeout_is_typed_and_not_retried(self):
        ClaudeCLIAdapter, WakeError, _ = adapter_api()
        timeout = subprocess.TimeoutExpired(["claude"], timeout=120)
        runner = RecordingRunner(timeout)
        with self.assertRaises(WakeError) as caught:
            ClaudeCLIAdapter(runner=runner).invoke(request(), "payload")
        self.assertEqual(caught.exception.code, "provider_timeout")
        self.assertEqual(len(runner.calls), 1)

    def test_missing_binary_is_typed(self):
        ClaudeCLIAdapter, WakeError, _ = adapter_api()
        runner = RecordingRunner(FileNotFoundError("missing"))
        with self.assertRaises(WakeError) as caught:
            ClaudeCLIAdapter(runner=runner).invoke(request(), "payload")
        self.assertEqual(caught.exception.code, "provider_binary_missing")


if __name__ == "__main__":
    unittest.main()
