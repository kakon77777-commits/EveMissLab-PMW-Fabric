from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import tempfile
from pathlib import Path
from urllib.error import URLError
import unittest

from tests.test_wake_contracts import valid_config, valid_request


def temporal_api():
    try:
        from eml_wake.models import ProviderResult, WakeConfig, WakeRequest
        from eml_wake.provider import FakeNotifier, FakeProviderAdapter
        from eml_wake.store import WakeStore
        from eml_wake.temporal import (
            CtclHttpTemporalProvider,
            FakeTemporalProvider,
            TemporalReceipt,
            UnavailableTemporalProvider,
        )
        from eml_wake.watchdog import WakeWatchdog
    except (ImportError, ModuleNotFoundError) as exc:
        raise AssertionError("CTCL temporal provider is not implemented") from exc
    return (
        ProviderResult,
        WakeConfig,
        WakeRequest,
        FakeNotifier,
        FakeProviderAdapter,
        WakeStore,
        CtclHttpTemporalProvider,
        FakeTemporalProvider,
        TemporalReceipt,
        UnavailableTemporalProvider,
        WakeWatchdog,
    )


class FakeHttpResponse:
    def __init__(self, body: dict):
        self.body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class RecordingOpener:
    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def __call__(self, request, *, timeout):
        self.calls.append((request, timeout))
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return FakeHttpResponse(self.outcome)


def registered_response() -> dict:
    return {
        "ok": True,
        "data": {
            "id": "ctcl:instant:11111111-2222-4333-8444-555555555555",
            "unix_ns": "1787559000000000000",
            "reference_timescale": "utc",
            "registered_at": "2026-08-24T08:10:00.000Z",
            "label": "wake ack",
            "meta": {"wake_id": "wake:test:001"},
            "from_wall_clock": True,
            "signature": {
                "alg": "Ed25519",
                "key_id": "ctcl-ed25519-1",
                "signed_fields": "instant_id|unix_ns|timescale",
                "value": "signature",
            },
            "retrieve": "/v1/instant/ctcl:instant:11111111-2222-4333-8444-555555555555",
            "share": "https://commoninstant.org/i/11111111-2222-4333-8444-555555555555",
            "encodings": {"unix_ns": "1787559000000000000"},
            "timescales": {"utc": "2026-08-24T08:10:00Z"},
        },
        "meta": {"api_version": "v1", "request_id": "req_test"},
    }


class CtclHttpTemporalProviderTests(unittest.TestCase):
    def test_posts_one_registration_and_preserves_full_receipt(self):
        _, _, _, _, _, _, CtclHttpTemporalProvider, _, _, _, _ = temporal_api()
        opener = RecordingOpener(registered_response())
        provider = CtclHttpTemporalProvider(opener=opener, timeout_s=7)

        receipt = provider.register("wake ack", {"wake_id": "wake:test:001"})

        self.assertEqual(len(opener.calls), 1)
        request, timeout = opener.calls[0]
        self.assertEqual(request.full_url, "https://commoninstant.org/v1/instants")
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(timeout, 7)
        self.assertEqual(request.headers["Content-type"], "application/json")
        self.assertEqual(request.headers.get("User-agent"), "EML-Wake/0.1 (+https://commoninstant.org)")
        self.assertEqual(json.loads(request.data), {"label": "wake ack", "meta": {"wake_id": "wake:test:001"}})
        self.assertEqual(receipt.status, "registered_anchor")
        self.assertEqual(receipt.instant_id, registered_response()["data"]["id"])
        self.assertEqual(receipt.receipt, registered_response()["data"])

    def test_invalid_success_shape_is_reported_unavailable_without_retry(self):
        _, _, _, _, _, _, CtclHttpTemporalProvider, _, _, _, _ = temporal_api()
        opener = RecordingOpener({"ok": True, "data": {"id": "not-an-instant"}})
        receipt = CtclHttpTemporalProvider(opener=opener).register("wake ack", {})
        self.assertEqual(receipt.status, "unavailable")
        self.assertEqual(receipt.error_code, "ctcl_response_invalid")
        self.assertEqual(len(opener.calls), 1)

    def test_network_failure_is_reported_unavailable_without_retry(self):
        _, _, _, _, _, _, CtclHttpTemporalProvider, _, _, _, _ = temporal_api()
        opener = RecordingOpener(URLError("offline"))
        receipt = CtclHttpTemporalProvider(opener=opener).register("wake ack", {})
        self.assertEqual(receipt.status, "unavailable")
        self.assertEqual(receipt.error_code, "ctcl_unavailable")
        self.assertEqual(len(opener.calls), 1)


class WatchdogTemporalIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.payload_root = self.root / "payloads"
        self.payload_root.mkdir()
        self.payload = self.payload_root / "message.md"
        self.payload.write_text("WAKE_OK\n", encoding="utf-8")
        (
            ProviderResult,
            WakeConfig,
            WakeRequest,
            FakeNotifier,
            FakeProviderAdapter,
            WakeStore,
            _,
            FakeTemporalProvider,
            TemporalReceipt,
            _,
            WakeWatchdog,
        ) = temporal_api()
        config_raw = valid_config()
        config_raw["allowed_payload_roots"] = [str(self.payload_root)]
        self.config = WakeConfig.from_dict(config_raw)
        self.request_raw = valid_request()
        self.request_raw.update(
            {
                "payload_ref": str(self.payload),
                "payload_sha256": hashlib.sha256(self.payload.read_bytes()).hexdigest().upper(),
            }
        )
        self.request = WakeRequest.from_dict(self.request_raw)
        self.provider_result = ProviderResult(
            provider="claude",
            model=self.request.model,
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
        self.FakeNotifier = FakeNotifier
        self.FakeProviderAdapter = FakeProviderAdapter
        self.WakeStore = WakeStore
        self.FakeTemporalProvider = FakeTemporalProvider
        self.TemporalReceipt = TemporalReceipt
        self.WakeWatchdog = WakeWatchdog

    def tearDown(self):
        self.tmp.cleanup()

    def build(self, temporal_receipt):
        store = self.WakeStore(self.root / f"wake-{temporal_receipt.status}", self.config)
        store.submit(self.request)
        provider = self.FakeProviderAdapter()
        provider.queue(self.provider_result)
        temporal = self.FakeTemporalProvider()
        temporal.queue(temporal_receipt)
        watchdog = self.WakeWatchdog(
            store,
            provider,
            self.FakeNotifier(),
            "watchdog:test",
            temporal=temporal,
            clock=lambda: datetime(2026, 8, 24, 8, 0, tzinfo=timezone.utc),
        )
        return store, provider, temporal, watchdog

    def test_registered_anchor_is_stored_in_ack(self):
        receipt = self.TemporalReceipt(
            status="registered_anchor",
            instant_id=registered_response()["data"]["id"],
            receipt=registered_response()["data"],
            error_code=None,
        )
        store, provider, temporal, watchdog = self.build(receipt)
        watchdog.process(self.request.wake_id)
        ack = store.status(self.request.wake_id)["record"]
        self.assertEqual(ack.get("request_time_ref"), self.request.created_time_ref)
        self.assertEqual(ack["temporal_evidence_status"], "registered_anchor")
        self.assertEqual(ack["temporal_instant_id"], receipt.instant_id)
        self.assertEqual(ack["temporal_receipt"], receipt.receipt)
        self.assertEqual(provider.invocation_count, 1)
        self.assertEqual(temporal.registration_count, 1)

    def test_ctcl_unavailable_preserves_provider_result_without_replay(self):
        receipt = self.TemporalReceipt(
            status="unavailable",
            instant_id=None,
            receipt=None,
            error_code="ctcl_unavailable",
        )
        store, provider, temporal, watchdog = self.build(receipt)
        watchdog.process(self.request.wake_id)
        ack = store.status(self.request.wake_id)["record"]
        self.assertEqual(ack["result_text"], "WAKE_OK")
        self.assertEqual(ack["temporal_evidence_status"], "unavailable")
        self.assertEqual(ack["temporal_error_code"], "ctcl_unavailable")
        self.assertIsNone(ack["temporal_instant_id"])
        self.assertEqual(provider.invocation_count, 1)
        self.assertEqual(temporal.registration_count, 1)
        watchdog.run_once()
        self.assertEqual(provider.invocation_count, 1)
        self.assertEqual(temporal.registration_count, 1)


if __name__ == "__main__":
    unittest.main()
