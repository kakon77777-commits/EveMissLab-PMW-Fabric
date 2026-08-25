from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

from .canonical import object_content_digest
from .errors import RelationContractError
from .references import validate_portable_ref


DIGEST_REF = re.compile(
    r"^sha256:(?:(?:[a-z0-9-]+):)?[0-9a-f]{64}$"
)


def require_exact(value: dict[str, Any], fields: set[str], subject: str) -> None:
    if not isinstance(value, dict):
        raise RelationContractError("contract_type_invalid", subject)
    unknown = sorted(set(value) - fields)
    missing = sorted(fields - set(value))
    if unknown:
        raise RelationContractError("unknown_field", f"{subject}:{unknown[0]}")
    if missing:
        raise RelationContractError("missing_field", f"{subject}:{missing[0]}")


def unique_refs(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or len(value) != len(set(value))
    ):
        raise RelationContractError("field_type_invalid", field)
    return tuple(validate_portable_ref(item, field) for item in value)


def unique_strings(value: Any, field: str, *, allow_empty: bool = False) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or (not allow_empty and not value)
        or any(not isinstance(item, str) or not item for item in value)
        or len(value) != len(set(value))
    ):
        raise RelationContractError("field_type_invalid", field)
    return tuple(value)


def validate_digest_ref(value: str, field: str) -> str:
    if not isinstance(value, str) or not DIGEST_REF.fullmatch(value):
        raise RelationContractError("digest_ref_invalid", field)
    return value


def validate_content_digest(value: dict[str, Any], subject: str) -> str:
    actual = value.get("content_digest")
    if actual != object_content_digest(value):
        raise RelationContractError("content_digest_mismatch", subject)
    return validate_digest_ref(actual, "content_digest")


def validate_version_parent(
    version: Any, parent_digest: Any, subject: str
) -> tuple[int, str | None]:
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise RelationContractError("version_parent_invalid", subject)
    if version == 1:
        if parent_digest is not None:
            raise RelationContractError("version_parent_invalid", subject)
        return version, None
    if not isinstance(parent_digest, str):
        raise RelationContractError("version_parent_invalid", subject)
    return version, validate_digest_ref(parent_digest, "parent_version_digest")


PARTY_PIN_FIELDS = {
    "schema",
    "party_ref",
    "party_kind",
    "resolver_profile_id",
    "resolver_schema_id",
    "resolver_source_ref",
    "resolver_source_digest",
    "state_view_digest",
    "state_head_ref",
    "party_status",
    "binding_ref",
    "binding_status",
    "binding_ambiguity",
    "adapter_verification_status",
    "observed_time_ref",
    "observed_time_status",
    "content_digest",
}


@dataclass(frozen=True)
class PartyEvidencePin:
    schema: str
    party_ref: str
    party_kind: str
    resolver_profile_id: str
    resolver_schema_id: str
    resolver_source_ref: str
    resolver_source_digest: str
    state_view_digest: str
    state_head_ref: str
    party_status: str
    binding_ref: str | None
    binding_status: str
    binding_ambiguity: bool
    adapter_verification_status: str
    observed_time_ref: str | None
    observed_time_status: str
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PartyEvidencePin":
        require_exact(value, PARTY_PIN_FIELDS, "party evidence pin")
        if (
            value["schema"] != "arcp/party-evidence-pin/0.1"
            or value["party_kind"]
            not in {"resident", "principal", "organization", "fixture"}
            or value["party_status"]
            not in {"active", "suspended", "expired", "tombstoned", "unmeasured"}
            or value["binding_status"]
            not in {
                "active",
                "suspended",
                "expired",
                "tombstoned",
                "ambiguous",
                "unmeasured",
            }
            or not isinstance(value["binding_ambiguity"], bool)
            or value["adapter_verification_status"]
            not in {"verified", "observed", "claimed", "unmeasured", "rejected"}
            or value["observed_time_status"]
            not in {"verified", "observed", "unmeasured", "rejected"}
        ):
            raise RelationContractError("party_evidence_invalid", value.get("party_ref", ""))
        binding_ref = value["binding_ref"]
        if binding_ref is not None:
            binding_ref = validate_portable_ref(binding_ref, "binding_ref")
        observed_time_ref = value["observed_time_ref"]
        if observed_time_ref is not None:
            observed_time_ref = validate_portable_ref(
                observed_time_ref, "observed_time_ref"
            )
        validate_content_digest(value, "party evidence pin")
        return cls(
            value["schema"],
            validate_portable_ref(value["party_ref"], "party_ref"),
            value["party_kind"],
            validate_portable_ref(value["resolver_profile_id"], "resolver_profile_id"),
            validate_portable_ref(value["resolver_schema_id"], "resolver_schema_id"),
            validate_portable_ref(value["resolver_source_ref"], "resolver_source_ref"),
            validate_digest_ref(value["resolver_source_digest"], "resolver_source_digest"),
            validate_digest_ref(value["state_view_digest"], "state_view_digest"),
            validate_portable_ref(value["state_head_ref"], "state_head_ref"),
            value["party_status"],
            binding_ref,
            value["binding_status"],
            value["binding_ambiguity"],
            value["adapter_verification_status"],
            observed_time_ref,
            value["observed_time_status"],
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
