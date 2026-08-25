from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Literal
from uuid import UUID

import jsonschema

from .contracts import load_local_contract
from .errors import IntegrationContractError


VerificationStatus = Literal[
    "verified", "observed", "claimed", "unmeasured", "rejected"
]
ENTITY_KINDS = {"arcp_agent", "principal", "unresolved"}
INSTANCE_KINDS = {"codex_thread", "session_uuid", "provider_session", "unresolved"}
PRINCIPAL_KINDS = {"provider_principal", "unresolved"}
FORBIDDEN_ENTITY_KINDS = {"runtime_tag", "pane", "role", "model_name"}
ARCP_AGENT = re.compile(r"^arcp:agent:([a-z0-9-]+):([0-9a-fA-F-]{36})$")


@dataclass(frozen=True)
class ExternalReference:
    value: str | None
    identifier_kind: str
    issuer: str
    verification_status: VerificationStatus
    evidence_refs: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExternalReference":
        item = cls(
            value=value.get("value"),
            identifier_kind=value["identifierKind"],
            issuer=value["issuer"],
            verification_status=value["verificationStatus"],
            evidence_refs=tuple(value.get("evidenceRefs", [])),
        )
        if item.verification_status not in {
            "verified",
            "observed",
            "claimed",
            "unmeasured",
            "rejected",
        }:
            raise IntegrationContractError(
                "invalid_reference_status", item.verification_status
            )
        if not item.issuer:
            raise IntegrationContractError(
                "reference_issuer_missing", item.identifier_kind
            )
        if any(not reference for reference in item.evidence_refs):
            raise IntegrationContractError(
                "empty_evidence_reference", item.identifier_kind
            )
        if item.verification_status in {"verified", "observed"} and not item.evidence_refs:
            code = (
                "verified_reference_missing_evidence"
                if item.verification_status == "verified"
                else "observed_reference_missing_evidence"
            )
            raise IntegrationContractError(code, item.identifier_kind)
        if item.identifier_kind == "unresolved" and item.value is not None:
            raise IntegrationContractError(
                "unresolved_reference_has_value", str(item.value)
            )
        return item


@dataclass(frozen=True)
class ParticipantBindingV1:
    binding_id: str
    pmw_workspace_id: str
    display_label: str
    entity_ref: ExternalReference
    instance_ref: ExternalReference | None
    provider_principal_ref: ExternalReference | None

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ParticipantBindingV1":
        presented_kind = value.get("entityRef", {}).get("identifierKind")
        if presented_kind in FORBIDDEN_ENTITY_KINDS:
            raise IntegrationContractError(
                "forbidden_entity_identifier_kind", presented_kind
            )
        try:
            jsonschema.validate(
                value, load_local_contract("participant-binding-v1.schema.json")
            )
        except jsonschema.ValidationError as error:
            raise IntegrationContractError(
                "participant_binding_schema_invalid", error.message
            ) from error
        entity = ExternalReference.from_dict(value["entityRef"])
        if entity.identifier_kind not in ENTITY_KINDS:
            raise IntegrationContractError(
                "forbidden_entity_identifier_kind", entity.identifier_kind
            )
        if entity.identifier_kind == "arcp_agent":
            if entity.value is None:
                raise IntegrationContractError("invalid_arcp_agent_id", "None")
            parse_arcp_agent_id(entity.value)
        instance = (
            None
            if value.get("instanceRef") is None
            else ExternalReference.from_dict(value["instanceRef"])
        )
        if instance and instance.identifier_kind not in INSTANCE_KINDS:
            raise IntegrationContractError(
                "forbidden_instance_identifier_kind", instance.identifier_kind
            )
        principal = (
            None
            if value.get("providerPrincipalRef") is None
            else ExternalReference.from_dict(value["providerPrincipalRef"])
        )
        if principal and principal.identifier_kind not in PRINCIPAL_KINDS:
            raise IntegrationContractError(
                "forbidden_provider_principal_kind", principal.identifier_kind
            )
        return cls(
            value["bindingId"],
            value["pmwWorkspaceId"],
            value["displayLabel"],
            entity,
            instance,
            principal,
        )


def parse_arcp_agent_id(value: str) -> tuple[str, str]:
    match = ARCP_AGENT.fullmatch(value)
    if not match:
        raise IntegrationContractError("invalid_arcp_agent_id", value)
    try:
        parsed = UUID(match.group(2))
    except ValueError as error:
        raise IntegrationContractError("invalid_arcp_agent_id", value) from error
    return match.group(1), str(parsed)
