from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_handoff.canonical import digest_ref, loads_strict
from eml_handoff.errors import HandoffError
from eml_handoff.models import (
    ClaimRecord,
    HandoffConfig,
    HandoffEnvelope,
    MaterializationRecord,
    ReceiptRecord,
)


def valid_config() -> dict:
    return {
        "schema_version": "eml-handoff/config-0.1",
        "allowed_source_roots": ["C:/fixture/shared"],
        "allowed_payload_extensions": [".md", ".json", ".txt"],
        "allowed_target_kinds": ["shared_topic", "task"],
        "allowed_authority_refs": ["principal:neo.k/cross-dialogue"],
        "default_max_payload_bytes": 1_048_576,
        "hard_max_payload_bytes": 4_194_304,
        "ctcl_endpoint": "https://commoninstant.org/v1/instants",
        "strict_reparse_checks": True,
    }


def valid_envelope() -> dict:
    return {
        "schema_version": "eml-handoff/envelope-0.1",
        "handoff_id": "handoff:test:001",
        "delivery_id": "delivery:test:001",
        "created_time_ref": "ctcl:instant:aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee",
        "temporal_evidence_status": "registered_anchor",
        "local_recorded_at": "2026-08-25T00:00:00Z",
        "claimed_sender_ref": "claim:sender",
        "claimed_sender_instance_ref": "claim:instance",
        "target_kind": "task",
        "target_ref": "task:pmw:test",
        "authority_ref": "principal:neo.k/cross-dialogue",
        "payload_ref": "payloads/example.md",
        "payload_media_type": "text/markdown",
        "payload_sha256": "A" * 64,
        "payload_bytes": 12,
        "sensitivity": "P1",
        "reply_to_handoff_id": None,
        "expires_at": None,
        "not_claimed": [
            "sender_authorship_verified",
            "recipient_awake",
            "recipient_identity_continuity",
            "payload_understood",
            "authority_to_act_on_payload",
            "fast_transport_delivered",
        ],
    }


def valid_claim() -> dict:
    return {
        "schema_version": "eml-handoff/claim-0.1",
        "handoff_id": "handoff:test:001",
        "envelope_core_digest": "sha256:eml-handoff-json-nfc-codepoint-v1:" + "1" * 64,
        "receiver_instance_ref": "thread:current",
        "receiver_binding_kind": "codex_thread",
        "receiver_entity_ref": None,
        "binding_evidence_ref": "host:exact-turn",
        "claim_authority_ref": "principal:neo.k/cross-dialogue",
        "observed_origin": None,
        "claimed_at": "2026-08-25T00:01:00Z",
    }


def valid_materialization() -> dict:
    return {
        "schema_version": "eml-handoff/materialization-0.1",
        "handoff_id": "handoff:test:001",
        "envelope_core_digest": "sha256:eml-handoff-json-nfc-codepoint-v1:" + "1" * 64,
        "payload_sha256": "A" * 64,
        "receiver_instance_ref": "thread:current",
        "materialized_at": "2026-08-25T00:02:00Z",
        "materialization_method": "local_file_read",
    }


def valid_receipt() -> dict:
    return {
        "schema_version": "eml-handoff/receipt-0.1",
        "handoff_id": "handoff:test:001",
        "envelope_core_digest": "sha256:eml-handoff-json-nfc-codepoint-v1:" + "1" * 64,
        "payload_sha256": "A" * 64,
        "receiver_instance_ref": "thread:current",
        "decision": "ACK",
        "response_handoff_id": None,
        "evidence_refs": ["host:exact-turn"],
        "recorded_time_ref": None,
        "local_recorded_at": "2026-08-25T00:03:00Z",
        "not_claimed": ["payload_understood"],
    }


class HandoffContractTests(unittest.TestCase):
    def test_valid_records_round_trip_without_field_collapse(self):
        pairs = (
            (HandoffConfig, valid_config()),
            (HandoffEnvelope, valid_envelope()),
            (ClaimRecord, valid_claim()),
            (MaterializationRecord, valid_materialization()),
            (ReceiptRecord, valid_receipt()),
        )
        for record_type, value in pairs:
            with self.subTest(record_type=record_type.__name__):
                self.assertEqual(record_type.from_dict(value).to_dict(), value)

    def test_delivery_id_is_excluded_from_core_digest_only(self):
        first = HandoffEnvelope.from_dict(valid_envelope())
        second = HandoffEnvelope.from_dict(
            {**valid_envelope(), "delivery_id": "delivery:test:002"}
        )
        self.assertEqual(first.core_digest, second.core_digest)
        self.assertNotEqual(digest_ref(first.to_dict()), digest_ref(second.to_dict()))
        self.assertTrue(
            first.core_digest.startswith("sha256:eml-handoff-json-nfc-codepoint-v1:")
        )

    def test_unknown_fields_and_p2_are_distinct_refusals(self):
        unknown = {**valid_envelope(), "extra": True}
        with self.assertRaises(HandoffError) as caught:
            HandoffEnvelope.from_dict(unknown)
        self.assertEqual(caught.exception.code, "unknown_field")

        p2 = {**valid_envelope(), "sensitivity": "P2"}
        with self.assertRaises(HandoffError) as caught:
            HandoffEnvelope.from_dict(p2)
        self.assertEqual(caught.exception.code, "sensitivity_not_shareable")

    def test_strict_json_rejects_floats_and_duplicate_keys(self):
        with self.assertRaises(HandoffError) as caught:
            loads_strict(b'{"n":1.5}')
        self.assertEqual(caught.exception.code, "unsupported_number")

        with self.assertRaises(HandoffError) as caught:
            loads_strict(b'{"a":1,"a":2}')
        self.assertEqual(caught.exception.code, "duplicate_key")

    def test_time_evidence_null_and_registered_are_distinct(self):
        unavailable = {
            **valid_envelope(),
            "created_time_ref": None,
            "temporal_evidence_status": "unavailable",
        }
        self.assertIsNone(HandoffEnvelope.from_dict(unavailable).created_time_ref)

        bad = {
            **valid_envelope(),
            "created_time_ref": None,
            "temporal_evidence_status": "registered_anchor",
        }
        with self.assertRaises(HandoffError) as caught:
            HandoffEnvelope.from_dict(bad)
        self.assertEqual(caught.exception.code, "temporal_evidence_mismatch")

    def test_not_claimed_contract_cannot_drop_required_boundary(self):
        value = deepcopy(valid_envelope())
        value["not_claimed"].remove("payload_understood")
        with self.assertRaises(HandoffError) as caught:
            HandoffEnvelope.from_dict(value)
        self.assertEqual(caught.exception.code, "not_claimed_incomplete")

    def test_config_limits_are_ordered_and_hard_capped(self):
        for default, hard in ((0, 1), (2, 1), (1, 4_194_305)):
            with self.subTest(default=default, hard=hard):
                with self.assertRaises(HandoffError) as caught:
                    HandoffConfig.from_dict(
                        {
                            **valid_config(),
                            "default_max_payload_bytes": default,
                            "hard_max_payload_bytes": hard,
                        }
                    )
                self.assertEqual(caught.exception.code, "payload_limit_invalid")


if __name__ == "__main__":
    unittest.main()
