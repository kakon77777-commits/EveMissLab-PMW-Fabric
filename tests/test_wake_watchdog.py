from __future__ import annotations

from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import hashlib
import tempfile
import threading
from pathlib import Path
import unittest

from tests.test_wake_contracts import valid_config, valid_request


def watchdog_api():
    try:
        from eml_wake.errors import WakeError
        from eml_wake.models import ProviderResult, WakeConfig, WakeRequest
        from eml_wake.provider import FakeNotifier, FakeProviderAdapter
        from eml_wake.store import WakeStore
        from eml_wake.watchdog import WakeWatchdog
    except (ImportError, ModuleNotFoundError) as exc:
        raise AssertionError("eml_wake watchdog orchestration is not implemented") from exc
    return WakeError, ProviderResult, WakeConfig, WakeRequest, FakeNotifier, FakeProviderAdapter, WakeStore, WakeWatchdog


class WakeWatchdogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.payload_root = self.root / "payloads"
        self.payload_root.mkdir()
        self.payload = self.payload_root / "message.md"
        self.payload.write_text("Return the marker: WAKE_OK\n", encoding="utf-8")

        (
            _,
            ProviderResult,
            WakeConfig,
            _,
            FakeNotifier,
            FakeProviderAdapter,
            WakeStore,
            WakeWatchdog,
        ) = watchdog_api()
        config_raw = valid_config()
        config_raw["allowed_payload_roots"] = [str(self.payload_root)]
        self.config = WakeConfig.from_dict(config_raw)
        self.store = WakeStore(self.root / "wake", self.config)
        self.provider = FakeProviderAdapter()
        self.notifier = FakeNotifier()
        self.watchdog = WakeWatchdog(
            store=self.store,
            provider=self.provider,
            notifier=self.notifier,
            watchdog_id="watchdog:test",
            clock=lambda: datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc),
        )
        self.success = ProviderResult(
            provider="claude",
            model="claude-haiku-4-5-20251001",
            provider_session_id="session:new",
            watchdog_invocation_id="invocation:test:001",
            result_text="WAKE_OK",
            is_error=False,
            subtype="success",
            stop_reason="end_turn",
            permission_denials=(),
            cost_microusd=27700,
            duration_ms=1234,
            api_error_status=None,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def request(self, **changes):
        _, _, _, WakeRequest, _, _, _, _ = watchdog_api()
        raw = valid_request()
        raw.update(
            {
                "payload_ref": str(self.payload),
                "payload_sha256": hashlib.sha256(self.payload.read_bytes()).hexdigest().upper(),
            }
        )
        raw.update(changes)
        return WakeRequest.from_dict(raw)

    def test_exact_instance_is_refused_before_provider_invocation(self):
        request = self.request(target_kind="exact_instance", spawn_allowed=False)
        self.store.submit(request)
        result = self.watchdog.process(request.wake_id)
        self.assertEqual(result.status, "exact_instance_spawn_refused")
        self.assertEqual(self.provider.invocation_count, 0)
        self.assertEqual(self.store.status(request.wake_id)["status"], "failed")

    def test_config_disallowed_target_is_refused_before_provider_invocation(self):
        _, _, WakeConfig, _, FakeNotifier, FakeProviderAdapter, WakeStore, WakeWatchdog = watchdog_api()
        config_raw = valid_config()
        config_raw["allowed_payload_roots"] = [str(self.payload_root)]
        config_raw["allowed_target_kinds"] = ["line"]
        config = WakeConfig.from_dict(config_raw)
        store = WakeStore(self.root / "denied", config)
        provider = FakeProviderAdapter()
        request = self.request()
        store.submit(request)
        result = WakeWatchdog(store, provider, FakeNotifier(), "watchdog:test").process(request.wake_id)
        self.assertEqual(result.status, "target_kind_not_allowed")
        self.assertEqual(provider.invocation_count, 0)

    def test_valid_wake_commits_one_ack_with_host_observed_provider_fields(self):
        request = self.request()
        self.store.submit(request)
        self.provider.queue(self.success)

        result = self.watchdog.process(request.wake_id)

        self.assertEqual(result.status, "acknowledged")
        self.assertEqual(self.provider.invocation_count, 1)
        ack = self.store.status(request.wake_id)["record"]
        self.assertEqual(ack["provider_session_id"], "session:new")
        self.assertEqual(ack["watchdog_invocation_id"], "invocation:test:001")
        self.assertEqual(ack["result_text"], "WAKE_OK")
        self.assertEqual(ack["payload_sha256"], request.payload_sha256)
        self.assertEqual(ack["model"], request.model)
        self.assertEqual(ack["cost_microusd"], 27700)
        self.assertEqual(ack["temporal_evidence_status"], "unavailable")
        self.assertEqual(self.provider.prompts[0], self.payload.read_bytes().decode("utf-8"))
        self.assertNotIn("MODEL != RESIDENT", self.provider.prompts[0])

    def test_three_delivery_paths_invoke_provider_once(self):
        first = self.request(delivery_id="delivery:1")
        self.store.submit(first)
        self.store.submit(self.request(delivery_id="delivery:2"))
        self.store.submit(self.request(delivery_id="delivery:3"))
        self.provider.queue(self.success)

        self.watchdog.run_once()
        self.watchdog.run_once()

        self.assertEqual(self.provider.invocation_count, 1)
        self.assertEqual(self.store.status(first.wake_id)["status"], "acknowledged")

    def test_two_concurrent_watchdogs_invoke_provider_once(self):
        _, _, _, _, FakeNotifier, FakeProviderAdapter, WakeStore, WakeWatchdog = watchdog_api()

        class BarrierStore(WakeStore):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.claim_barrier = threading.Barrier(2)

            def claim(self, wake_id, watchdog_id):
                self.claim_barrier.wait(timeout=2)
                return super().claim(wake_id, watchdog_id)

        store = BarrierStore(self.root / "concurrent", self.config)
        provider = FakeProviderAdapter()
        provider.queue(self.success)
        store.submit(self.request())
        first = WakeWatchdog(store, provider, FakeNotifier(), "watchdog:one")
        second = WakeWatchdog(store, provider, FakeNotifier(), "watchdog:two")

        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(first.process, "wake:test:001"), pool.submit(second.process, "wake:test:001")]
            results = [future.result(timeout=3) for future in futures]

        self.assertEqual(provider.invocation_count, 1)
        self.assertEqual(sorted(result.status for result in results), ["acknowledged", "claimed_incomplete"])

    def test_claim_without_ack_is_never_retried(self):
        request = self.request()
        self.store.submit(request)
        self.store.claim(request.wake_id, "watchdog:crashed")
        results = self.watchdog.run_once()
        self.assertEqual(results, [])
        result = self.watchdog.process(request.wake_id)
        self.assertEqual(result.status, "claimed_incomplete")
        self.assertEqual(self.provider.invocation_count, 0)

    def test_payload_digest_failure_does_not_claim_or_invoke(self):
        request = self.request(payload_sha256="B" * 64)
        self.store.submit(request)
        result = self.watchdog.process(request.wake_id)
        self.assertEqual(result.status, "payload_integrity_failed")
        self.assertEqual(self.provider.invocation_count, 0)
        self.assertFalse(self.store.claim_path(request.wake_id).exists())

    def test_expired_request_does_not_claim_or_invoke(self):
        request = self.request(expires_at="2026-08-24T07:59:59Z")
        self.store.submit(request)
        result = self.watchdog.process(request.wake_id)
        self.assertEqual(result.status, "request_expired")
        self.assertEqual(self.provider.invocation_count, 0)
        self.assertFalse(self.store.claim_path(request.wake_id).exists())

    def test_provider_busy_records_failure_without_retry(self):
        WakeError, _, _, _, _, _, _, _ = watchdog_api()
        request = self.request()
        self.store.submit(request)
        self.provider.queue(WakeError("provider_busy", "service busy"))
        result = self.watchdog.process(request.wake_id)
        self.assertEqual(result.status, "provider_busy")
        self.assertEqual(self.provider.invocation_count, 1)
        self.assertEqual(self.store.status(request.wake_id)["record"]["code"], "provider_busy")
        self.watchdog.run_once()
        self.assertEqual(self.provider.invocation_count, 1)

    def test_notification_failure_does_not_change_ack_completion(self):
        request = self.request()
        self.store.submit(request)
        self.provider.queue(self.success)
        self.notifier.queue(accepted=False, error_code="ephemeral_route_expired")

        result = self.watchdog.process(request.wake_id)

        self.assertEqual(result.status, "acknowledged")
        self.assertEqual(self.store.status(request.wake_id)["status"], "acknowledged")
        notifications = list(self.store.notifications_dir.rglob("*.json"))
        self.assertEqual(len(notifications), 1)
        self.assertEqual(self.notifier.notification_count, 1)


if __name__ == "__main__":
    unittest.main()
