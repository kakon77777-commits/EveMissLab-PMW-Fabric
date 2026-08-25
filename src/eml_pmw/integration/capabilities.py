from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import jsonschema

from .contracts import load_contract, load_local_contract, verify_contract_lock
from .errors import IntegrationContractError


@dataclass(frozen=True)
class NegotiationResult:
    status: Literal["compatible", "incompatible", "unmeasured"]
    reason_codes: tuple[str, ...]


def load_integration_profile() -> dict[str, Any]:
    profile = load_local_contract("integration-profile-v1.json")
    try:
        jsonschema.validate(
            profile, load_local_contract("integration-profile-v1.schema.json")
        )
    except jsonschema.ValidationError as error:
        raise IntegrationContractError(
            "integration_profile_invalid", error.message
        ) from error
    return profile


def _contains_credential_key(value: Any) -> bool:
    forbidden = {
        "authtoken",
        "accesstoken",
        "apikey",
        "secret",
        "password",
        "authorization",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            normalized = str(key).replace("_", "").replace("-", "").lower()
            if normalized in forbidden or _contains_credential_key(item):
                return True
    elif isinstance(value, list):
        return any(_contains_credential_key(item) for item in value)
    return False


def negotiate_mrmic(document: dict[str, Any] | None) -> NegotiationResult:
    if not isinstance(document, dict):
        return NegotiationResult(
            "unmeasured", ("capability_document_unmeasured",)
        )
    if _contains_credential_key(document):
        return NegotiationResult(
            "incompatible", ("capability_document_contains_credential",)
        )
    profile = load_integration_profile()
    lock = verify_contract_lock()
    if not lock.valid:
        return NegotiationResult(
            "incompatible", ("upstream_contract_lock_invalid",)
        )
    if lock.source_commit != profile["mrmic"]["sourceCommit"]:
        return NegotiationResult(
            "incompatible", ("upstream_source_commit_mismatch",)
        )
    try:
        jsonschema.validate(
            document, load_contract("mrmic-capabilities-v1.schema.json")
        )
    except jsonschema.ValidationError:
        return NegotiationResult("incompatible", ("capability_schema_invalid",))
    required = profile["mrmic"]
    checks = (
        (document["mrmicVersion"] == required["mrmicVersion"], "mrmic_version_mismatch"),
        (document["canvasSchemaVersion"] == required["canvasSchemaVersion"], "canvas_schema_mismatch"),
        (document["mcpProtocolProfile"]["protocolVersion"] == required["mcpProtocolVersion"], "mcp_protocol_version_mismatch"),
        (document["mcpProtocolProfile"]["profile"] == required["mcpProfile"], "mcp_profile_mismatch"),
        (required["projectionMode"] in document["projectionModes"], "required_projection_mode_missing"),
        (required["authMode"] in document["authModes"], "required_auth_mode_missing"),
        (document["resourcePortal"]["supported"] is True, "native_portal_not_supported"),
        (document["resourcePortal"]["schemaVersion"] == required["projectionMode"], "portal_schema_mismatch"),
        (document["runtimePresence"]["supported"] is True, "runtime_presence_not_supported"),
        (document["runtimePresence"]["durable"] is False, "runtime_presence_must_be_ephemeral"),
        (document["runtimePresence"]["schemaVersion"] == required["runtimePresenceSchema"], "runtime_presence_schema_mismatch"),
        (document["livePortalHost"]["supported"] is True, "live_host_not_supported"),
        (document["livePortalHost"]["stateVersion"] == required["livePortalHostState"], "live_host_state_mismatch"),
    )
    reasons = tuple(code for passed, code in checks if not passed)
    return NegotiationResult(
        "compatible" if not reasons else "incompatible", reasons
    )
