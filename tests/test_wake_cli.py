from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import tempfile
from pathlib import Path
import unittest

from tests.test_wake_contracts import valid_config, valid_request


def cli_api():
    try:
        from eml_wake.cli import main, watch_loop
        from eml_wake.models import ProviderResult
        from eml_wake.provider import FakeNotifier, FakeProviderAdapter
        from eml_wake.temporal import TemporalReceipt, FakeTemporalProvider
    except (ImportError, ModuleNotFoundError) as exc:
        raise AssertionError("eml_wake CLI is not implemented") from exc
    return main, watch_loop, ProviderResult, FakeNotifier, FakeProviderAdapter, TemporalReceipt, FakeTemporalProvider


class StopAfterSleep:
    def __init__(self):
        self.stopped = False
        self.sleep_calls = []

    def is_set(self):
        return self.stopped

    def sleep(self, seconds):
        self.sleep_calls.append(seconds)
        self.stopped = True


class WakeCliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / "wake"
        self.payload_root = self.base / "payloads"
        self.payload_root.mkdir()
        self.payload = self.payload_root / "message.md"
        self.payload.write_text("Return WAKE_OK\n", encoding="utf-8")
        config = valid_config()
        config["allowed_payload_roots"] = [str(self.payload_root)]
        self.config_file = self.base / "config.json"
        self.config_file.write_text(json.dumps(config), encoding="utf-8")
        self.request_file = self.base / "request.json"
        request = valid_request()
        request.update(
            {
                "payload_ref": str(self.payload),
                "payload_sha256": hashlib.sha256(self.payload.read_bytes()).hexdigest().upper(),
            }
        )
        self.request = request
        self.request_file.write_text(json.dumps(request), encoding="utf-8")
        (
            self.main,
            self.watch_loop,
            ProviderResult,
            self.FakeNotifier,
            self.FakeProviderAdapter,
            self.TemporalReceipt,
            self.FakeTemporalProvider,
        ) = cli_api()
        self.provider_result = ProviderResult(
            provider="claude",
            model=request["model"],
            provider_session_id="session:new",
            watchdog_invocation_id="invocation:test",
            result_text="WAKE_OK",
            is_error=False,
            subtype="success",
            stop_reason="end_turn",
            permission_denials=(),
            cost_microusd=27700,
            duration_ms=1200,
            api_error_status=None,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def argv(self, *tail):
        return ["--root", str(self.root), "--config", str(self.config_file), *tail]

    def run_cli(self, *tail, provider=None, temporal=None, notifier=None):
        stream = io.StringIO()
        try:
            code = self.main(
                self.argv(*tail),
                provider=provider,
                temporal=temporal,
                notifier=notifier,
                stdout=stream,
            )
        except SystemExit as exc:
            self.fail(f"CLI command is not implemented or parsed: exit {exc.code}")
        text = stream.getvalue()
        self.assertTrue(text.endswith("\n"))
        self.assertFalse(text.endswith("\n\n"))
        return code, json.loads(text)

    def test_submit_then_duplicate_have_typed_canonical_output(self):
        code, first = self.run_cli("submit", str(self.request_file))
        self.assertEqual(code, 0)
        self.assertEqual(first["kind"], "created")

        duplicate = dict(self.request)
        duplicate["delivery_id"] = "delivery:test:002"
        duplicate_file = self.base / "duplicate.json"
        duplicate_file.write_text(json.dumps(duplicate), encoding="utf-8")
        code, second = self.run_cli("submit", str(duplicate_file))
        self.assertEqual(code, 0)
        self.assertEqual(second["kind"], "duplicate")

    def test_create_uses_local_tools_policy_and_registered_ctcl_anchor(self):
        temporal = self.FakeTemporalProvider()
        temporal.queue(
            self.TemporalReceipt(
                "registered_anchor",
                "ctcl:instant:aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
                {"id": "ctcl:instant:aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"},
                None,
            )
        )
        code, value = self.run_cli(
            "create",
            "--payload",
            str(self.payload),
            "--sender",
            "agent://example/sender",
            "--authority",
            "principal:neo.k/cross-dialogue",
            "--target-ref",
            "worker:claude:generic",
            "--model",
            "claude-haiku-4-5-20251001",
            "--tools-policy",
            "no_tools",
            "--expires-seconds",
            "600",
            "--max-budget-microusd",
            "100000",
            "--timeout-ms",
            "120000",
            temporal=temporal,
        )
        self.assertEqual(code, 0)
        self.assertEqual(value["kind"], "created")
        self.assertEqual(value["request"]["created_time_ref"], "ctcl:instant:aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")
        self.assertEqual(value["request"]["allowed_tools"], [])
        self.assertEqual(value["request"]["authority_ref"], "principal:neo.k/cross-dialogue")
        self.assertEqual(temporal.registration_count, 1)

    def test_create_refuses_unknown_tools_policy_before_ctcl(self):
        temporal = self.FakeTemporalProvider()
        code, value = self.run_cli(
            "create",
            "--payload",
            str(self.payload),
            "--sender",
            "agent://example/sender",
            "--authority",
            "principal:neo.k/cross-dialogue",
            "--target-ref",
            "worker:claude:generic",
            "--model",
            "claude-haiku-4-5-20251001",
            "--tools-policy",
            "not-configured",
            temporal=temporal,
        )
        self.assertEqual(code, 2)
        self.assertEqual(value["error"]["code"], "tools_policy_not_found")
        self.assertEqual(temporal.registration_count, 0)

    def test_create_ctcl_unavailable_writes_no_request(self):
        temporal = self.FakeTemporalProvider()
        temporal.queue(self.TemporalReceipt("unavailable", None, None, "ctcl_unavailable"))
        code, value = self.run_cli(
            "create",
            "--payload",
            str(self.payload),
            "--sender",
            "agent://example/sender",
            "--authority",
            "principal:neo.k/cross-dialogue",
            "--target-ref",
            "worker:claude:generic",
            "--model",
            "claude-haiku-4-5-20251001",
            "--tools-policy",
            "no_tools",
            temporal=temporal,
        )
        self.assertEqual(code, 1)
        self.assertEqual(value["error"]["code"], "ctcl_request_anchor_unavailable")
        self.assertEqual(list((self.root / "requests").glob("*.json")), [])

    def test_run_once_and_status_return_ack(self):
        self.run_cli("submit", str(self.request_file))
        provider = self.FakeProviderAdapter()
        provider.queue(self.provider_result)
        temporal = self.FakeTemporalProvider()
        temporal.queue(self.TemporalReceipt("unavailable", None, None, "fixture"))

        code, result = self.run_cli(
            "run-once",
            provider=provider,
            temporal=temporal,
            notifier=self.FakeNotifier(),
        )
        self.assertEqual(code, 0)
        self.assertEqual(result["results"][0]["status"], "acknowledged")

        code, status = self.run_cli("status", self.request["wake_id"])
        self.assertEqual(code, 0)
        self.assertEqual(status["status"], "acknowledged")
        self.assertEqual(status["record"]["provider_session_id"], "session:new")

    def test_exact_instance_refusal_uses_exit_two_and_zero_provider_calls(self):
        request = dict(self.request)
        request.update({"target_kind": "exact_instance", "spawn_allowed": False})
        path = self.base / "exact.json"
        path.write_text(json.dumps(request), encoding="utf-8")
        self.run_cli("submit", str(path))
        provider = self.FakeProviderAdapter()
        code, result = self.run_cli(
            "run-once",
            provider=provider,
            temporal=self.FakeTemporalProvider(),
            notifier=self.FakeNotifier(),
        )
        self.assertEqual(code, 2)
        self.assertEqual(result["results"][0]["status"], "exact_instance_spawn_refused")
        self.assertEqual(provider.invocation_count, 0)

    def test_claimed_incomplete_status_uses_exit_three(self):
        self.run_cli("submit", str(self.request_file))
        from eml_wake.models import WakeConfig
        from eml_wake.store import WakeStore

        config = WakeConfig.from_dict(json.loads(self.config_file.read_text(encoding="utf-8")))
        store = WakeStore(self.root, config)
        store.claim(self.request["wake_id"], "watchdog:crashed")
        code, result = self.run_cli("status", self.request["wake_id"])
        self.assertEqual(code, 3)
        self.assertEqual(result["status"], "claimed_incomplete")

    def test_unreadable_and_contract_invalid_inputs_are_distinct(self):
        code, missing = self.run_cli("submit", str(self.base / "missing.json"))
        self.assertEqual(code, 1)
        self.assertEqual(missing["error"]["code"], "input_unreadable")

        bad = self.base / "bad.json"
        bad.write_text('{"schema_version":"wrong"}', encoding="utf-8")
        code, invalid = self.run_cli("submit", str(bad))
        self.assertEqual(code, 2)
        self.assertIn(invalid["error"]["code"], {"missing_field", "schema_version_unsupported"})

    def test_watch_loop_processes_once_then_sleeps_when_idle(self):
        self.run_cli("submit", str(self.request_file))
        from eml_wake.models import WakeConfig
        from eml_wake.store import WakeStore
        from eml_wake.watchdog import WakeWatchdog

        config = WakeConfig.from_dict(json.loads(self.config_file.read_text(encoding="utf-8")))
        store = WakeStore(self.root, config)
        provider = self.FakeProviderAdapter()
        provider.queue(self.provider_result)
        temporal = self.FakeTemporalProvider()
        temporal.queue(self.TemporalReceipt("unavailable", None, None, "fixture"))
        watchdog = WakeWatchdog(
            store,
            provider,
            self.FakeNotifier(),
            "watchdog:test",
            temporal=temporal,
            clock=lambda: datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc),
        )
        stop = StopAfterSleep()
        self.watch_loop(watchdog, poll_interval_ms=250, stop_event=stop, sleeper=stop.sleep)
        self.assertEqual(provider.invocation_count, 1)
        self.assertEqual(stop.sleep_calls, [0.25])


if __name__ == "__main__":
    unittest.main()
