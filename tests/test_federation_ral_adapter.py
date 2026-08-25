from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import unittest

import jsonschema

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_wake.canonical import canonical_bytes
from eml_pmw.federation.adoption import ReceiverAdoptionReceipt
from eml_pmw.federation.models import RealmRef, ReplicaRef
from eml_pmw.federation.ral_adapter import (
    RalAdapterManifest,
    ral_adapter_digest,
    ral_view_to_event,
    verify_ral_schema_pin,
)
from eml_pmw.integration.contracts import load_local_contract
from tests.federation_helpers import assert_error_code, valid_event


def manifest_value(**overrides):
    value = {
        "schema": "pmw.ral-public-projection-adapter/v1",
        "adapter_profile_id": "pmw-adapter:sedb-ral:limen-v0.2",
        "source_manifest_schema": "sedb-ral.fabric-seam-source-manifest/0.1",
        "source_manifest_digest": "sha256:sedb-ral-json-nfc-codepoint-v1:f22a06d08c6d3a0c4a0ab60ded7b9696585c8d1cb08f59ff465e80a87b270529",
        "source_schema_id": "https://evemisslab.com/schemas/limen/ral-view-v0.2.json",
        "source_schema_version": "0.2",
        "source_repository": "https://github.com/kakon77777-commits/SEDB-RAL-SEDB-Residency-Attestation-Layer",
        "source_commit": "077606f08576b38e93762d7eb4d8720b36766fc1",
        "source_schema_bytes": 6029,
        "source_schema_sha256": "32aefbb92345538b0320930e237f35791c0c43c5a1f7e40eace5d7248d803373",
        "source_profile_ref": "sedb-ral.fabric-seam-source/v0.1",
        "carrier_event_kind": "ral.public_projection.snapshot",
        "subject_mapping": {
            "source_field": "view_id",
            "target_template": "ral-public-view:{realm_id}:{view_id}",
        },
        "ral_disclosure_class": "public",
        "fabric_payload_class": "P0",
        "correction_mapping": "source_semantics_preserved",
        "tombstone_mapping": "source_semantics_preserved",
        "not_claimed": [
            "ral_schema_vendored",
            "ral_authority_activated",
            "ral_head_mutated",
            "private_access",
        ],
    }
    value.update(deepcopy(overrides))
    value["manifest_digest"] = ral_adapter_digest(value)
    return value


def public_view():
    return {
        "schema": "limen.ral-view/0.2",
        "profile": "sedb-ral/0.3.0",
        "view_id": "view:fixture",
        "sequence": 1,
        "authority_head": "sha256:sedb-ral-json-nfc-codepoint-v1:" + "1" * 64,
        "binding_head": "sha256:sedb-ral-json-nfc-codepoint-v1:" + "2" * 64,
        "ledger_head": "sha256:sedb-ral-chain-v1:" + "3" * 64,
        "bindings": [],
        "projection_conflicts": [],
        "source_refs": ["fixture:source"],
        "not_claimed": [
            "private_access",
            "host_observation",
            "host_enforcement",
            "registry_authority",
            "identity_merge",
        ],
    }


def adoption_value(event, **overrides):
    value = {
        "schema": "pmw.receiver-adoption-receipt/v1",
        "receipt_id": "adoption:fixture:1",
        "event_id": event.event_id,
        "event_digest": event.core_digest,
        "receiver_realm_id": "realm:b",
        "source_schema_id": manifest_value()["source_schema_id"],
        "source_schema_sha256": manifest_value()["source_schema_sha256"],
        "source_ledger_head": public_view()["ledger_head"],
        "source_view_digest": "sha256:sedb-ral-json-nfc-codepoint-v1:" + "4" * 64,
        "decision": "adopted",
        "reason_codes": [],
        "receiver_observation_refs": ["observation:fixture"],
        "authority_verification_status": "not_required",
        "not_claimed": [
            "ral_head_mutated",
            "registry_commit",
            "authority_granted",
            "resident_identity_continuity",
            "source_history_rewritten",
        ],
    }
    value.update(deepcopy(overrides))
    value["receipt_digest"] = ReceiverAdoptionReceipt.digest_for(value)
    return value


class FederationRalAdapterTests(unittest.TestCase):
    def test_checked_in_manifest_is_the_exact_approved_j1_pin(self):
        path = ROOT / "examples" / "federation" / "ral-adapter-manifest.json"
        value = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(value, manifest_value())
        self.assertEqual(
            RalAdapterManifest.from_dict(value).source_manifest_digest,
            "sha256:sedb-ral-json-nfc-codepoint-v1:f22a06d08c6d3a0c4a0ab60ded7b9696585c8d1cb08f59ff465e80a87b270529",
        )

    def test_manifest_and_receipt_schemas_meta_validate(self):
        manifest_schema = load_local_contract(
            "ral-public-projection-adapter-v1.schema.json"
        )
        receipt_schema = load_local_contract(
            "receiver-adoption-receipt-v1.schema.json"
        )
        jsonschema.Draft202012Validator.check_schema(manifest_schema)
        jsonschema.Draft202012Validator.check_schema(receipt_schema)
        jsonschema.validate(manifest_value(), manifest_schema)

    def test_wrong_ral_schema_hash_fails_before_view_parsing(self):
        manifest = RalAdapterManifest.from_dict(manifest_value())

        with assert_error_code(self, "ral_schema_digest_mismatch"):
            verify_ral_schema_pin(manifest, b"{not-json")

    def test_public_view_maps_deterministically_to_realm_qualified_event(self):
        manifest = RalAdapterManifest.from_dict(manifest_value())
        event_parts = valid_event()
        realm = RealmRef.from_dict(event_parts["realm_ref"])
        replica = ReplicaRef.from_dict(event_parts["replica_ref"])
        view_bytes = canonical_bytes(public_view())

        first = ral_view_to_event(manifest, view_bytes, realm, replica, 7)
        second = ral_view_to_event(manifest, view_bytes, realm, replica, 7)

        self.assertEqual(first, second)
        self.assertEqual(first.subject_ref, "ral-public-view:realm:a:view:fixture")
        self.assertEqual(first.event_kind, "ral.public_projection.snapshot")
        self.assertEqual(first.fabric_payload_class, "P0")
        self.assertIsNone(first.authority_ref)

    def test_non_public_disclosure_cannot_map_to_carrier_class(self):
        with assert_error_code(self, "ral_disclosure_not_public"):
            RalAdapterManifest.from_dict(
                manifest_value(ral_disclosure_class="private")
            )

    def test_adoption_receipt_has_no_ral_mutation_or_authority_fields(self):
        manifest = RalAdapterManifest.from_dict(manifest_value())
        event_parts = valid_event()
        event = ral_view_to_event(
            manifest,
            canonical_bytes(public_view()),
            RealmRef.from_dict(event_parts["realm_ref"]),
            ReplicaRef.from_dict(event_parts["replica_ref"]),
            1,
        )
        receipt = ReceiverAdoptionReceipt.from_dict(adoption_value(event))
        self.assertEqual(receipt.decision, "adopted")
        for forbidden in ("ral_head_after", "registry_commit", "authority_granted"):
            with self.subTest(forbidden=forbidden):
                with assert_error_code(self, "unknown_field"):
                    ReceiverAdoptionReceipt.from_dict(
                        adoption_value(event, **{forbidden: "forbidden"})
                    )


if __name__ == "__main__":
    unittest.main()
