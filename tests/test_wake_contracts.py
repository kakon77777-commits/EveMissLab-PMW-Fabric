from __future__ import annotations

import copy
import unittest


def contract_api():
    try:
        from eml_wake.errors import WakeError
        from eml_wake.models import WakeConfig, WakeRequest
    except ModuleNotFoundError as exc:
        raise AssertionError("eml_wake request contracts are not implemented") from exc
    return WakeConfig, WakeRequest, WakeError


def valid_request() -> dict:
    return {
        "schema_version": "eml-wake/request-0.1",
        "wake_id": "wake:test:001",
        "delivery_id": "delivery:test:001",
        "created_time_ref": "ctcl:instant:11111111-2222-4333-8444-555555555555",
        "expires_at": "2099-01-01T00:00:00Z",
        "sender_claim": "agent://example/sender",
        "target_kind": "generic_worker",
        "target_ref": "worker:claude:test",
        "spawn_allowed": True,
        "authority_ref": "authority:test",
        "payload_ref": "payloads/test.md",
        "payload_sha256": "A" * 64,
        "context_package_ref": None,
        "reply_policy": "durable_ack_only",
        "provider": "claude",
        "model": "claude-haiku-4-5-20251001",
        "allowed_tools": [],
        "permission_mode": "dontAsk",
        "max_budget_microusd": 100000,
        "timeout_ms": 120000,
        "requested_output_format": "json",
        "not_claimed": [],
    }


def valid_config() -> dict:
    return {
        "schema_version": "eml-wake/config-0.1",
        "allowed_payload_roots": ["D:/example/handoffs"],
        "allowed_context_roots": [],
        "allowed_target_kinds": ["generic_worker", "line"],
        "allowed_models": ["claude-haiku-4-5-20251001"],
        "allowed_tools_by_policy": {"no_tools": []},
        "permission_modes": ["dontAsk"],
        "maximum_budget_microusd": 200000,
        "maximum_timeout_ms": 180000,
        "claude_binary": "claude",
        "poll_interval_ms": 500,
        "ctcl_endpoint": "https://commoninstant.org/v1/instants",
        "strict_reparse_checks": True,
    }


class WakeRequestTests(unittest.TestCase):
    def test_valid_request_round_trips_and_normalizes_hash(self):
        _, WakeRequest, _ = contract_api()
        request = WakeRequest.from_dict(valid_request())
        self.assertEqual(request.wake_id, "wake:test:001")
        self.assertEqual(request.payload_sha256, "A" * 64)
        self.assertEqual(request.to_dict(), valid_request())

    def test_delivery_id_does_not_change_core_digest(self):
        _, WakeRequest, _ = contract_api()
        first = WakeRequest.from_dict(valid_request())
        changed = valid_request()
        changed["delivery_id"] = "delivery:test:002"
        second = WakeRequest.from_dict(changed)
        self.assertEqual(first.core_digest, second.core_digest)
        self.assertNotEqual(first.to_dict(), second.to_dict())

    def test_unknown_field_is_rejected(self):
        _, WakeRequest, WakeError = contract_api()
        value = valid_request()
        value["mystery"] = True
        with self.assertRaises(WakeError) as caught:
            WakeRequest.from_dict(value)
        self.assertEqual(caught.exception.code, "unknown_field")

    def test_missing_model_and_tools_are_rejected(self):
        _, WakeRequest, WakeError = contract_api()
        for field in ("model", "allowed_tools"):
            value = valid_request()
            del value[field]
            with self.subTest(field=field), self.assertRaises(WakeError) as caught:
                WakeRequest.from_dict(value)
            self.assertEqual(caught.exception.code, "missing_field")

    def test_float_budget_is_rejected(self):
        _, WakeRequest, WakeError = contract_api()
        value = valid_request()
        value["max_budget_microusd"] = 100000.0
        with self.assertRaises(WakeError) as caught:
            WakeRequest.from_dict(value)
        self.assertEqual(caught.exception.code, "field_type_invalid")

    def test_spawn_target_requires_spawn_allowed(self):
        _, WakeRequest, WakeError = contract_api()
        value = valid_request()
        value["spawn_allowed"] = False
        with self.assertRaises(WakeError) as caught:
            WakeRequest.from_dict(value)
        self.assertEqual(caught.exception.code, "spawn_authority_missing")

    def test_exact_instance_can_be_recorded_only_with_spawn_disabled(self):
        _, WakeRequest, WakeError = contract_api()
        value = valid_request()
        value.update({"target_kind": "exact_instance", "spawn_allowed": False})
        request = WakeRequest.from_dict(value)
        self.assertEqual(request.target_kind, "exact_instance")
        value["spawn_allowed"] = True
        with self.assertRaises(WakeError) as caught:
            WakeRequest.from_dict(value)
        self.assertEqual(caught.exception.code, "exact_instance_spawn_forbidden")

    def test_line_target_requires_an_explicit_context_package(self):
        _, WakeRequest, WakeError = contract_api()
        value = valid_request()
        value.update({"target_kind": "line", "context_package_ref": None})
        with self.assertRaises(WakeError) as caught:
            WakeRequest.from_dict(value)
        self.assertEqual(caught.exception.code, "line_context_missing")

        value["context_package_ref"] = "D:/allowed/context.json"
        self.assertEqual(WakeRequest.from_dict(value).target_kind, "line")

    def test_malformed_ctcl_id_and_non_utc_expiry_are_rejected(self):
        _, WakeRequest, WakeError = contract_api()
        mutations = [
            ("created_time_ref", "yesterday", "ctcl_ref_invalid"),
            ("expires_at", "2099-01-01T08:00:00+08:00", "utc_time_required"),
        ]
        for field, value, code in mutations:
            raw = valid_request()
            raw[field] = value
            with self.subTest(field=field), self.assertRaises(WakeError) as caught:
                WakeRequest.from_dict(raw)
            self.assertEqual(caught.exception.code, code)

    def test_unsupported_provider_and_output_format_are_rejected(self):
        _, WakeRequest, WakeError = contract_api()
        mutations = [
            ("provider", "unknown", "provider_unsupported"),
            ("requested_output_format", "text", "output_format_unsupported"),
        ]
        for field, value, code in mutations:
            raw = valid_request()
            raw[field] = value
            with self.subTest(field=field), self.assertRaises(WakeError) as caught:
                WakeRequest.from_dict(raw)
            self.assertEqual(caught.exception.code, code)


class WakeConfigTests(unittest.TestCase):
    def test_valid_config_round_trips(self):
        WakeConfig, _, _ = contract_api()
        config = WakeConfig.from_dict(valid_config())
        self.assertEqual(config.to_dict(), valid_config())

    def test_config_rejects_unknown_fields(self):
        WakeConfig, _, WakeError = contract_api()
        raw = valid_config()
        raw["default_model"] = "claude-opus-5"
        with self.assertRaises(WakeError) as caught:
            WakeConfig.from_dict(raw)
        self.assertEqual(caught.exception.code, "unknown_field")

    def test_config_requires_at_least_one_model_and_payload_root(self):
        WakeConfig, _, WakeError = contract_api()
        for field in ("allowed_models", "allowed_payload_roots"):
            raw = valid_config()
            raw[field] = []
            with self.subTest(field=field), self.assertRaises(WakeError) as caught:
                WakeConfig.from_dict(raw)
            self.assertEqual(caught.exception.code, "config_allowlist_empty")


if __name__ == "__main__":
    unittest.main()
