from __future__ import annotations

import hashlib
from typing import Any

import jsonschema
from eml_wake.canonical import canonical_bytes, loads_strict
from eml_wake.errors import WakeError
from eml_pmw.federation.errors import FederationError
from eml_pmw.federation.ral_adapter import (
    RalAdapterManifest,
    verify_ral_schema_pin,
)

from .canonical import object_content_digest
from .errors import RelationContractError
from .models_common import PartyEvidencePin


RAL_CANON = "sedb-ral-json-nfc-codepoint-v1"
RAL_DOMAIN = b"SEDB-RAL-CANONICAL\x00" + RAL_CANON.encode("ascii") + b"\x00"


def _convert_federation_error(error: FederationError) -> RelationContractError:
    return RelationContractError(error.code, error.message)


def _ral_view_digest(view_bytes: bytes) -> str:
    digest = hashlib.sha256(RAL_DOMAIN + view_bytes).hexdigest()
    return f"sha256:{RAL_CANON}:{digest}"


class RalPartyEvidenceAdapter:
    """Resolve one current public RAL binding without accepting a RAL path."""

    def __init__(self, manifest: RalAdapterManifest, schema_bytes: bytes):
        if not isinstance(manifest, RalAdapterManifest):
            raise RelationContractError("ral_manifest_invalid", "manifest")
        try:
            schema = verify_ral_schema_pin(manifest, schema_bytes)
        except FederationError as error:
            raise _convert_federation_error(error) from error
        try:
            jsonschema.Draft202012Validator.check_schema(schema)
        except jsonschema.SchemaError as error:
            raise RelationContractError(
                "ral_schema_invalid", manifest.source_schema_id
            ) from error
        self.manifest = manifest
        self._validator = jsonschema.Draft202012Validator(schema)

    def resolve_party(
        self,
        view_bytes: bytes | None,
        *,
        resident_id: str,
        instance_id: str,
        expected_ledger_head: str,
        expected_view_digest: str,
    ) -> PartyEvidencePin:
        if view_bytes is None:
            raise RelationContractError(
                "ral_current_view_required", resident_id
            )
        if not isinstance(view_bytes, bytes):
            raise RelationContractError("ral_view_invalid", resident_id)
        try:
            view = loads_strict(view_bytes)
        except WakeError as error:
            raise RelationContractError("ral_view_invalid", resident_id) from error
        if not isinstance(view, dict) or view_bytes != canonical_bytes(view):
            raise RelationContractError("ral_view_not_canonical", resident_id)
        if next(self._validator.iter_errors(view), None) is not None:
            raise RelationContractError("ral_view_schema_invalid", resident_id)

        ledger_head = str(view["ledger_head"])
        if ledger_head != expected_ledger_head:
            raise RelationContractError("ral_head_stale", resident_id)
        view_digest = _ral_view_digest(view_bytes)
        if view_digest != expected_view_digest:
            raise RelationContractError("ral_view_stale", resident_id)

        resident_bindings = [
            item
            for item in view["bindings"]
            if item["resident_id"] == resident_id
        ]
        if not resident_bindings:
            raise RelationContractError("party_not_found", resident_id)
        active_bindings = [
            item
            for item in resident_bindings
            if item["status"] == "active"
            and item["valid_from_sequence"] <= view["sequence"]
            and (
                item["valid_until_sequence"] is None
                or view["sequence"] < item["valid_until_sequence"]
            )
        ]
        if not active_bindings:
            raise RelationContractError("party_binding_inactive", resident_id)
        active_instances = {item["instance_id"] for item in active_bindings}
        if len(active_instances) != 1:
            raise RelationContractError("party_binding_ambiguous", resident_id)
        if instance_id not in active_instances:
            raise RelationContractError("party_instance_not_found", instance_id)
        matches = [
            item for item in active_bindings if item["instance_id"] == instance_id
        ]
        if len(matches) != 1:
            raise RelationContractError("party_binding_ambiguous", resident_id)
        binding = matches[0]
        if any(
            binding["binding_id"] in conflict["binding_refs"]
            or (
                conflict["namespace"] == "codex_thread"
                and conflict["locator"] == binding["native_thread_id"]
            )
            for conflict in view["projection_conflicts"]
        ):
            raise RelationContractError("party_binding_ambiguous", resident_id)

        value: dict[str, Any] = {
            "schema": "arcp/party-evidence-pin/0.1",
            "party_ref": resident_id,
            "party_kind": "resident",
            "resolver_profile_id": (
                f"sedb-ral-public-view:v{self.manifest.source_schema_version}"
            ),
            "resolver_schema_id": self.manifest.source_schema_id,
            "resolver_source_ref": self.manifest.source_repository,
            "resolver_source_digest": self.manifest.source_manifest_digest,
            "state_view_digest": view_digest,
            "state_head_ref": ledger_head,
            "party_status": "active",
            "binding_ref": binding["binding_id"],
            "binding_status": "active",
            "binding_ambiguity": False,
            "adapter_verification_status": "verified",
            "observed_time_ref": None,
            "observed_time_status": "unmeasured",
            "content_digest": "",
        }
        value["content_digest"] = object_content_digest(value)
        return PartyEvidencePin.from_dict(value)
