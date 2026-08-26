from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path
import tempfile
import unittest

from eml_wake.canonical import canonical_bytes
from eml_pmw.federation.ral_adapter import (
    RalAdapterManifest,
    ral_adapter_digest,
)
from eml_pmw.relations.authority import ral_pin_sufficient
from eml_pmw.relations.ral_adapter import RalPartyEvidenceAdapter
from scripts.check_federation_offline_boundary import scan_offline_boundary
from tests.relation_contract_helpers import assert_relation_error


RAL_CANON = "sedb-ral-json-nfc-codepoint-v1"
RAL_DOMAIN = b"SEDB-RAL-CANONICAL\x00" + RAL_CANON.encode("ascii") + b"\x00"
SCHEMA_ID = "https://evemisslab.com/schemas/limen/ral-view-v0.2.json"


def test_schema_bytes() -> bytes:
    string = {"type": "string", "minLength": 1}
    nullable_string = {"type": ["string", "null"], "minLength": 1}
    binding = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "binding_id",
            "provider",
            "adapter_kind",
            "identifier_kind",
            "identifier_components",
            "native_thread_id",
            "native_session_id",
            "session_match_policy",
            "resident_id",
            "instance_id",
            "continuity_line_id",
            "speaker_label",
            "status",
            "valid_from_sequence",
            "valid_until_sequence",
            "lineage_from_thread_ids",
            "supersedes_binding_id",
            "source_refs",
        ],
        "properties": {
            "binding_id": string,
            "provider": {"const": "openai"},
            "adapter_kind": {"const": "codex_app_task_tool"},
            "identifier_kind": {"const": "codex_thread"},
            "identifier_components": {"const": ["native_thread_id"]},
            "native_thread_id": string,
            "native_session_id": {"const": None},
            "session_match_policy": {"const": "not_applicable_for_profile"},
            "resident_id": string,
            "instance_id": string,
            "continuity_line_id": string,
            "speaker_label": string,
            "status": {"enum": ["active", "suspended", "tombstoned", "withdrawn"]},
            "valid_from_sequence": {"type": "integer", "minimum": 1},
            "valid_until_sequence": {"oneOf": [{"type": "null"}, {"type": "integer", "minimum": 1}]},
            "lineage_from_thread_ids": {"type": "array", "uniqueItems": True, "items": string},
            "supersedes_binding_id": nullable_string,
            "source_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": string},
        },
    }
    conflict = {
        "type": "object",
        "additionalProperties": False,
        "required": ["conflict_id", "error_code", "namespace", "locator", "binding_refs", "source_refs"],
        "properties": {
            "conflict_id": string,
            "error_code": string,
            "namespace": string,
            "locator": string,
            "binding_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": string},
            "source_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": string},
        },
    }
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": SCHEMA_ID,
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema",
            "profile",
            "view_id",
            "sequence",
            "authority_head",
            "binding_head",
            "ledger_head",
            "bindings",
            "projection_conflicts",
            "source_refs",
            "not_claimed",
        ],
        "properties": {
            "schema": {"const": "limen.ral-view/0.2"},
            "profile": {"const": "sedb-ral/0.3.0"},
            "view_id": string,
            "sequence": {"type": "integer", "minimum": 1},
            "authority_head": string,
            "binding_head": string,
            "ledger_head": string,
            "bindings": {"type": "array", "uniqueItems": True, "items": binding},
            "projection_conflicts": {"type": "array", "uniqueItems": True, "items": conflict},
            "source_refs": {"type": "array", "minItems": 1, "uniqueItems": True, "items": string},
            "not_claimed": {"type": "array", "minItems": 1, "uniqueItems": True, "items": string},
        },
    }
    return canonical_bytes(schema)


def manifest_for(schema_bytes: bytes) -> RalAdapterManifest:
    value = {
        "schema": "pmw.ral-public-projection-adapter/v1",
        "adapter_profile_id": "pmw-adapter:sedb-ral:limen-v0.2",
        "source_manifest_schema": "sedb-ral.fabric-seam-source-manifest/0.1",
        "source_manifest_digest": "sha256:sedb-ral-json-nfc-codepoint-v1:" + "1" * 64,
        "source_schema_id": SCHEMA_ID,
        "source_schema_version": "0.2",
        "source_repository": "https://github.com/example/sedb-ral",
        "source_commit": "2" * 40,
        "source_schema_bytes": len(schema_bytes),
        "source_schema_sha256": hashlib.sha256(schema_bytes).hexdigest(),
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
        "manifest_digest": "",
    }
    value["manifest_digest"] = ral_adapter_digest(value)
    return RalAdapterManifest.from_dict(value)


def public_view() -> dict:
    return {
        "schema": "limen.ral-view/0.2",
        "profile": "sedb-ral/0.3.0",
        "view_id": "ral-view:fixture",
        "sequence": 7,
        "authority_head": "sha256:sedb-ral-json-nfc-codepoint-v1:" + "3" * 64,
        "binding_head": "sha256:sedb-ral-json-nfc-codepoint-v1:" + "4" * 64,
        "ledger_head": "sha256:sedb-ral-chain-v1:" + "5" * 64,
        "bindings": [
            {
                "binding_id": "binding:fixture:a:1",
                "provider": "openai",
                "adapter_kind": "codex_app_task_tool",
                "identifier_kind": "codex_thread",
                "identifier_components": ["native_thread_id"],
                "native_thread_id": "thread:fixture:a:1",
                "native_session_id": None,
                "session_match_policy": "not_applicable_for_profile",
                "resident_id": "resident:fixture:a",
                "instance_id": "instance:fixture:a:1",
                "continuity_line_id": "line:fixture:a",
                "speaker_label": "Fixture A",
                "status": "active",
                "valid_from_sequence": 1,
                "valid_until_sequence": None,
                "lineage_from_thread_ids": [],
                "supersedes_binding_id": None,
                "source_refs": ["event:fixture:a", "address:fixture:a"],
            }
        ],
        "projection_conflicts": [],
        "source_refs": ["event:fixture:a"],
        "not_claimed": [
            "private_access",
            "host_observation",
            "host_enforcement",
            "registry_authority",
            "identity_merge",
        ],
    }


def ral_view_digest(value: dict) -> str:
    digest = hashlib.sha256(RAL_DOMAIN + canonical_bytes(value)).hexdigest()
    return f"sha256:{RAL_CANON}:{digest}"


class MutationTrapBytes(bytes):
    def write(self, *_args, **_kwargs):
        raise AssertionError("adapter attempted to mutate source")


class RelationContractRalAdapterTests(unittest.TestCase):
    def setUp(self):
        self.schema_bytes = test_schema_bytes()
        self.manifest = manifest_for(self.schema_bytes)
        self.adapter = RalPartyEvidenceAdapter(self.manifest, self.schema_bytes)
        self.view = public_view()
        self.view_bytes = canonical_bytes(self.view)
        self.expected = {
            "resident_id": "resident:fixture:a",
            "instance_id": "instance:fixture:a:1",
            "expected_ledger_head": self.view["ledger_head"],
            "expected_view_digest": ral_view_digest(self.view),
        }

    def test_verified_current_unique_binding_produces_sufficient_pin(self):
        pin = self.adapter.resolve_party(self.view_bytes, **self.expected)
        self.assertEqual(pin.party_ref, "resident:fixture:a")
        self.assertEqual(pin.binding_ref, "binding:fixture:a:1")
        self.assertEqual(pin.adapter_verification_status, "verified")
        self.assertTrue(
            ral_pin_sufficient(
                pin,
                current_ledger_head=self.view["ledger_head"],
                current_view_digest=ral_view_digest(self.view),
            )
        )

    def test_schema_pin_is_verified_before_view_parsing(self):
        with assert_relation_error(self, "ral_schema_digest_mismatch"):
            RalPartyEvidenceAdapter(self.manifest, self.schema_bytes + b" ")

    def test_missing_noncanonical_or_schema_invalid_view_fails_closed(self):
        with assert_relation_error(self, "ral_current_view_required"):
            self.adapter.resolve_party(None, **self.expected)
        with assert_relation_error(self, "ral_view_not_canonical"):
            self.adapter.resolve_party(self.view_bytes + b"\n", **self.expected)
        invalid = {**self.view, "unexpected": True}
        with assert_relation_error(self, "ral_view_schema_invalid"):
            self.adapter.resolve_party(canonical_bytes(invalid), **self.expected)

    def test_head_and_view_digest_drift_are_distinct(self):
        with assert_relation_error(self, "ral_head_stale"):
            self.adapter.resolve_party(
                self.view_bytes,
                **{**self.expected, "expected_ledger_head": "ral-head:other"},
            )
        with assert_relation_error(self, "ral_view_stale"):
            self.adapter.resolve_party(
                self.view_bytes,
                **{**self.expected, "expected_view_digest": "sha256:" + "9" * 64},
            )

    def test_ambiguous_conflicted_or_inactive_binding_fails_closed(self):
        second = deepcopy(self.view["bindings"][0])
        second.update(
            {
                "binding_id": "binding:fixture:a:2",
                "instance_id": "instance:fixture:a:2",
                "native_thread_id": "thread:fixture:a:2",
            }
        )
        ambiguous = deepcopy(self.view)
        ambiguous["bindings"].append(second)
        conflicted = deepcopy(self.view)
        conflicted["projection_conflicts"] = [
            {
                "conflict_id": "conflict:fixture:a",
                "error_code": "instance_binding_ambiguous",
                "namespace": "codex_thread",
                "locator": "thread:fixture:a:1",
                "binding_refs": ["binding:fixture:a:1"],
                "source_refs": ["event:fixture:a"],
            }
        ]
        inactive = deepcopy(self.view)
        inactive["bindings"][0]["status"] = "suspended"
        for label, value, code in (
            ("ambiguous", ambiguous, "party_binding_ambiguous"),
            ("conflicted", conflicted, "party_binding_ambiguous"),
            ("inactive", inactive, "party_binding_inactive"),
        ):
            with self.subTest(label=label):
                with assert_relation_error(self, code):
                    self.adapter.resolve_party(
                        canonical_bytes(value),
                        **{
                            **self.expected,
                            "expected_view_digest": ral_view_digest(value),
                        },
                    )

    def test_source_is_read_only_and_head_advance_invalidates_pin(self):
        source = MutationTrapBytes(self.view_bytes)
        pin = self.adapter.resolve_party(source, **self.expected)
        self.assertFalse(
            ral_pin_sufficient(
                pin,
                current_ledger_head="sha256:sedb-ral-chain-v1:" + "6" * 64,
                current_view_digest=ral_view_digest(self.view),
            )
        )
        self.assertFalse(hasattr(self.adapter, "commit"))
        self.assertFalse(hasattr(self.adapter, "register"))

    def test_relations_package_forbids_sedb_ral_implementation_imports(self):
        package = Path(__file__).resolve().parents[1] / "src" / "eml_pmw" / "relations"
        self.assertEqual(scan_offline_boundary(package), [])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "mutation.py").write_text(
                "from sedb_ral.operations import RegistrarOperations\n",
                encoding="utf-8",
            )
            self.assertIn(
                "forbidden_import:sedb_ral",
                [item.code for item in scan_offline_boundary(root)],
            )


if __name__ == "__main__":
    unittest.main()
