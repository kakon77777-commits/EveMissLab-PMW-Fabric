from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .canonical import digest_ref


@dataclass(frozen=True)
class HandoffConfig:
    schema_version: str
    allowed_source_roots: tuple[str, ...]
    allowed_payload_extensions: tuple[str, ...]
    allowed_target_kinds: tuple[str, ...]
    allowed_authority_refs: tuple[str, ...]
    default_max_payload_bytes: int
    hard_max_payload_bytes: int
    ctcl_endpoint: str
    strict_reparse_checks: bool

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "HandoffConfig":
        from .contracts import validate_config_dict

        normalized = validate_config_dict(value)
        for field in (
            "allowed_source_roots",
            "allowed_payload_extensions",
            "allowed_target_kinds",
            "allowed_authority_refs",
        ):
            normalized[field] = tuple(normalized[field])
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in (
            "allowed_source_roots",
            "allowed_payload_extensions",
            "allowed_target_kinds",
            "allowed_authority_refs",
        ):
            value[field] = list(value[field])
        return value


@dataclass(frozen=True)
class HandoffEnvelope:
    schema_version: str
    handoff_id: str
    delivery_id: str
    created_time_ref: str | None
    temporal_evidence_status: str
    local_recorded_at: str
    claimed_sender_ref: str
    claimed_sender_instance_ref: str
    target_kind: str
    target_ref: str
    authority_ref: str
    payload_ref: str
    payload_media_type: str
    payload_sha256: str
    payload_bytes: int
    sensitivity: str
    reply_to_handoff_id: str | None
    expires_at: str | None
    not_claimed: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "HandoffEnvelope":
        from .contracts import validate_envelope_dict

        normalized = validate_envelope_dict(value)
        normalized["not_claimed"] = tuple(normalized["not_claimed"])
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["not_claimed"] = list(self.not_claimed)
        return value

    def core_dict(self) -> dict[str, Any]:
        value = self.to_dict()
        value.pop("delivery_id")
        return value

    @property
    def core_digest(self) -> str:
        return digest_ref(self.core_dict())


@dataclass(frozen=True)
class ClaimRecord:
    schema_version: str
    handoff_id: str
    envelope_core_digest: str
    receiver_instance_ref: str | None
    receiver_binding_kind: str
    receiver_entity_ref: str | None
    binding_evidence_ref: str | None
    claim_authority_ref: str
    observed_origin: str | None
    claimed_at: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ClaimRecord":
        from .contracts import validate_claim_dict

        return cls(**validate_claim_dict(value))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MaterializationRecord:
    schema_version: str
    handoff_id: str
    envelope_core_digest: str
    payload_sha256: str
    receiver_instance_ref: str | None
    materialized_at: str
    materialization_method: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "MaterializationRecord":
        from .contracts import validate_materialization_dict

        return cls(**validate_materialization_dict(value))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ReceiptRecord:
    schema_version: str
    handoff_id: str
    envelope_core_digest: str
    payload_sha256: str
    receiver_instance_ref: str | None
    decision: str
    response_handoff_id: str | None
    evidence_refs: tuple[str, ...]
    recorded_time_ref: str | None
    local_recorded_at: str
    not_claimed: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReceiptRecord":
        from .contracts import validate_receipt_dict

        normalized = validate_receipt_dict(value)
        normalized["evidence_refs"] = tuple(normalized["evidence_refs"])
        normalized["not_claimed"] = tuple(normalized["not_claimed"])
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence_refs"] = list(self.evidence_refs)
        value["not_claimed"] = list(self.not_claimed)
        return value
