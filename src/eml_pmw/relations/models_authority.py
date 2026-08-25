from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .errors import RelationContractError
from .models_common import (
    require_exact,
    unique_refs,
    unique_strings,
    validate_content_digest,
    validate_digest_ref,
)
from .references import validate_portable_ref
from .temporal import NormalizedInstantEvidence, compare_instants


GRANT_AUTHORITY_FIELDS = {
    "schema",
    "grant_authority_evidence_id",
    "grantor_party_ref",
    "authority_source_ref",
    "resolver_profile_id",
    "permitted_lifecycle_actions",
    "permitted_contract_scope",
    "valid_from",
    "expires_at",
    "dependency_refs",
    "content_digest",
}
REPRESENTATION_FIELDS = {
    "schema",
    "representation_grant_id",
    "principal_party_ref",
    "representative_ref",
    "representative_kind",
    "allowed_lifecycle_actions",
    "contract_scope",
    "relation_scope",
    "valid_from",
    "expires_at",
    "issued_at",
    "revocable",
    "redelegable",
    "grant_authority_ref",
    "acceptance_evidence_refs",
    "party_evidence_pin_refs",
    "content_digest",
}
ACCEPTANCE_FIELDS = {
    "schema",
    "acceptance_id",
    "party_ref",
    "target_kind",
    "target_id",
    "target_version",
    "target_digest",
    "representation_grant_ref",
    "representation_grant_digest",
    "party_evidence_pin_refs",
    "acceptance_evidence_refs",
    "acceptance_evidence_root_refs",
    "accepted_at",
    "content_digest",
}


@dataclass(frozen=True)
class GrantAuthorityEvidence:
    schema: str
    grant_authority_evidence_id: str
    grantor_party_ref: str
    authority_source_ref: str
    resolver_profile_id: str
    permitted_lifecycle_actions: tuple[str, ...]
    permitted_contract_scope: tuple[str, ...]
    valid_from: NormalizedInstantEvidence
    expires_at: NormalizedInstantEvidence
    dependency_refs: tuple[str, ...]
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "GrantAuthorityEvidence":
        require_exact(value, GRANT_AUTHORITY_FIELDS, "grant authority evidence")
        valid_from = NormalizedInstantEvidence.from_dict(value["valid_from"])
        expires_at = NormalizedInstantEvidence.from_dict(value["expires_at"])
        if (
            value["schema"] != "arcp/grant-authority-evidence/0.1"
            or compare_instants(valid_from, expires_at) != "before"
        ):
            raise RelationContractError(
                "grant_authority_invalid", value.get("grant_authority_evidence_id", "")
            )
        actions = unique_strings(
            value["permitted_lifecycle_actions"], "permitted_lifecycle_actions"
        )
        contract_scope = unique_refs(
            value["permitted_contract_scope"], "permitted_contract_scope"
        )
        dependencies = unique_refs(
            value["dependency_refs"], "dependency_refs", allow_empty=True
        )
        validate_content_digest(value, "grant authority evidence")
        return cls(
            value["schema"],
            validate_portable_ref(
                value["grant_authority_evidence_id"],
                "grant_authority_evidence_id",
            ),
            validate_portable_ref(value["grantor_party_ref"], "grantor_party_ref"),
            validate_portable_ref(value["authority_source_ref"], "authority_source_ref"),
            validate_portable_ref(value["resolver_profile_id"], "resolver_profile_id"),
            actions,
            contract_scope,
            valid_from,
            expires_at,
            dependencies,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "grant_authority_evidence_id": self.grant_authority_evidence_id,
            "grantor_party_ref": self.grantor_party_ref,
            "authority_source_ref": self.authority_source_ref,
            "resolver_profile_id": self.resolver_profile_id,
            "permitted_lifecycle_actions": list(self.permitted_lifecycle_actions),
            "permitted_contract_scope": list(self.permitted_contract_scope),
            "valid_from": self.valid_from.to_dict(),
            "expires_at": self.expires_at.to_dict(),
            "dependency_refs": list(self.dependency_refs),
            "content_digest": self.content_digest,
        }


@dataclass(frozen=True)
class RepresentationGrant:
    schema: str
    representation_grant_id: str
    principal_party_ref: str
    representative_ref: str
    representative_kind: str
    allowed_lifecycle_actions: tuple[str, ...]
    contract_scope: tuple[str, ...]
    relation_scope: tuple[str, ...]
    valid_from: NormalizedInstantEvidence
    expires_at: NormalizedInstantEvidence
    issued_at: NormalizedInstantEvidence
    revocable: bool
    redelegable: bool
    grant_authority_ref: str
    acceptance_evidence_refs: tuple[str, ...]
    party_evidence_pin_refs: tuple[str, ...]
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RepresentationGrant":
        require_exact(value, REPRESENTATION_FIELDS, "representation grant")
        if (
            value["schema"] != "arcp/representation-grant/0.1"
            or value["representative_kind"] not in {"entity", "instance"}
            or value["revocable"] is not True
            or value["redelegable"] is not False
            or not isinstance(value["allowed_lifecycle_actions"], list)
            or not value["allowed_lifecycle_actions"]
        ):
            raise RelationContractError(
                "representation_grant_invalid",
                value.get("representation_grant_id", ""),
            )
        actions = unique_strings(
            value["allowed_lifecycle_actions"], "allowed_lifecycle_actions"
        )
        contract_scope = unique_refs(
            value["contract_scope"], "contract_scope", allow_empty=True
        )
        relation_scope = unique_refs(
            value["relation_scope"], "relation_scope", allow_empty=True
        )
        if not contract_scope and not relation_scope:
            raise RelationContractError(
                "representation_grant_invalid", "scope"
            )
        issued_at = NormalizedInstantEvidence.from_dict(value["issued_at"])
        valid_from = NormalizedInstantEvidence.from_dict(value["valid_from"])
        expires_at = NormalizedInstantEvidence.from_dict(value["expires_at"])
        if compare_instants(issued_at, valid_from) not in {"before", "equal"} or (
            compare_instants(valid_from, expires_at) != "before"
        ):
            raise RelationContractError(
                "representation_grant_invalid", "time"
            )
        acceptance = unique_refs(
            value["acceptance_evidence_refs"], "acceptance_evidence_refs"
        )
        pins = unique_refs(
            value["party_evidence_pin_refs"], "party_evidence_pin_refs"
        )
        validate_content_digest(value, "representation grant")
        return cls(
            value["schema"],
            validate_portable_ref(
                value["representation_grant_id"], "representation_grant_id"
            ),
            validate_portable_ref(
                value["principal_party_ref"], "principal_party_ref"
            ),
            validate_portable_ref(value["representative_ref"], "representative_ref"),
            value["representative_kind"],
            actions,
            contract_scope,
            relation_scope,
            valid_from,
            expires_at,
            issued_at,
            True,
            False,
            validate_portable_ref(
                value["grant_authority_ref"], "grant_authority_ref"
            ),
            acceptance,
            pins,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "representation_grant_id": self.representation_grant_id,
            "principal_party_ref": self.principal_party_ref,
            "representative_ref": self.representative_ref,
            "representative_kind": self.representative_kind,
            "allowed_lifecycle_actions": list(self.allowed_lifecycle_actions),
            "contract_scope": list(self.contract_scope),
            "relation_scope": list(self.relation_scope),
            "valid_from": self.valid_from.to_dict(),
            "expires_at": self.expires_at.to_dict(),
            "issued_at": self.issued_at.to_dict(),
            "revocable": self.revocable,
            "redelegable": self.redelegable,
            "grant_authority_ref": self.grant_authority_ref,
            "acceptance_evidence_refs": list(self.acceptance_evidence_refs),
            "party_evidence_pin_refs": list(self.party_evidence_pin_refs),
            "content_digest": self.content_digest,
        }


@dataclass(frozen=True)
class PartyAcceptance:
    schema: str
    acceptance_id: str
    party_ref: str
    target_kind: str
    target_id: str
    target_version: int
    target_digest: str
    representation_grant_ref: str
    representation_grant_digest: str
    party_evidence_pin_refs: tuple[str, ...]
    acceptance_evidence_refs: tuple[str, ...]
    acceptance_evidence_root_refs: tuple[str, ...]
    accepted_at: NormalizedInstantEvidence
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PartyAcceptance":
        require_exact(value, ACCEPTANCE_FIELDS, "party acceptance")
        target_kind = value["target_kind"]
        target_id = value["target_id"]
        if (
            value["schema"] != "arcp/party-acceptance/0.1"
            or target_kind not in {"relation", "contract"}
            or not isinstance(target_id, str)
            or not target_id.startswith(f"{target_kind}:")
        ):
            raise RelationContractError(
                "acceptance_target_kind_mismatch", str(target_id)
            )
        if (
            isinstance(value["target_version"], bool)
            or not isinstance(value["target_version"], int)
            or value["target_version"] < 1
        ):
            raise RelationContractError("acceptance_invalid", "target_version")
        pins = unique_refs(
            value["party_evidence_pin_refs"], "party_evidence_pin_refs"
        )
        evidence = unique_refs(
            value["acceptance_evidence_refs"], "acceptance_evidence_refs"
        )
        roots = unique_refs(
            value["acceptance_evidence_root_refs"],
            "acceptance_evidence_root_refs",
        )
        accepted_at = NormalizedInstantEvidence.from_dict(value["accepted_at"])
        validate_content_digest(value, "party acceptance")
        return cls(
            value["schema"],
            validate_portable_ref(value["acceptance_id"], "acceptance_id"),
            validate_portable_ref(value["party_ref"], "party_ref"),
            target_kind,
            validate_portable_ref(target_id, "target_id"),
            value["target_version"],
            validate_digest_ref(value["target_digest"], "target_digest"),
            validate_portable_ref(
                value["representation_grant_ref"], "representation_grant_ref"
            ),
            validate_digest_ref(
                value["representation_grant_digest"],
                "representation_grant_digest",
            ),
            pins,
            evidence,
            roots,
            accepted_at,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in (
            "party_evidence_pin_refs",
            "acceptance_evidence_refs",
            "acceptance_evidence_root_refs",
        ):
            value[field] = list(value[field])
        value["accepted_at"] = self.accepted_at.to_dict()
        return value
