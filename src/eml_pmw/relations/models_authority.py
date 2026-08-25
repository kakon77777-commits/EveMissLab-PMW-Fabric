from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .canonical import object_content_digest
from .errors import RelationContractError
from .models_common import (
    require_exact,
    unique_refs,
    unique_strings,
    validate_content_digest,
    validate_digest_ref,
    validate_version_parent,
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
COMMITMENT_FIELDS = {
    "schema",
    "commitment_id",
    "version",
    "parent_version_digest",
    "contract_ref",
    "contract_digest",
    "obligated_party_ref",
    "beneficiary_party_refs",
    "action_class",
    "scope",
    "due_or_review_at",
    "status",
    "execution_refs",
    "content_digest",
}
CANDIDATE_FIELDS = {
    "schema",
    "candidate_id",
    "subject_entity_ref",
    "run_ref",
    "action_intent_ref",
    "action_intent_digest",
    "relation_refs",
    "contract_ref",
    "contract_digest",
    "active_lifecycle_head",
    "representation_grant_refs",
    "representation_grant_digests",
    "party_evidence_pin_refs",
    "party_evidence_set_digest",
    "requested_resource_scope",
    "requested_action_scope",
    "risk",
    "approval_mode",
    "continuity_precondition",
    "expires_at",
    "clock_profile_id",
    "activation_time_ref",
    "activation_time_evidence_digest",
    "evaluator_profile_id",
    "evaluator_policy_version",
    "candidate_status",
    "reason_codes",
    "content_digest",
}
RECEIPT_FIELDS = {
    "schema",
    "candidate_ref",
    "candidate_digest",
    "evaluator_profile_id",
    "evaluator_implementation_version",
    "evaluator_policy_version",
    "evaluated_evidence_set_digest",
    "authority_resolution",
    "evaluated_at",
    "receipt_digest",
}
RESOLUTION_FIELDS = {
    "schema",
    "resolution_id",
    "run_id",
    "action_id",
    "action_hash",
    "status",
    "sources",
    "subject_entity_ref",
    "resource_scope",
    "relation_refs",
    "contract_refs",
    "revocable",
    "expires_at",
    "continuity_precondition",
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


@dataclass(frozen=True)
class CommitmentRecord:
    schema: str
    commitment_id: str
    version: int
    parent_version_digest: str | None
    contract_ref: str
    contract_digest: str
    obligated_party_ref: str
    beneficiary_party_refs: tuple[str, ...]
    action_class: str
    scope: tuple[str, ...]
    due_or_review_at: NormalizedInstantEvidence
    status: str
    execution_refs: tuple[str, ...]
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "CommitmentRecord":
        require_exact(value, COMMITMENT_FIELDS, "commitment")
        version, parent = validate_version_parent(
            value["version"], value["parent_version_digest"], "commitment"
        )
        if (
            value["schema"] != "arcp/commitment/0.1"
            or not isinstance(value["action_class"], str)
            or not value["action_class"]
            or value["status"]
            not in {"planned", "active", "satisfied", "breached", "waived", "terminated"}
        ):
            raise RelationContractError("commitment_invalid", value.get("commitment_id", ""))
        beneficiaries = unique_refs(
            value["beneficiary_party_refs"], "beneficiary_party_refs"
        )
        scope = unique_strings(value["scope"], "scope")
        executions = unique_refs(
            value["execution_refs"], "execution_refs", allow_empty=True
        )
        due = NormalizedInstantEvidence.from_dict(value["due_or_review_at"])
        validate_content_digest(value, "commitment")
        return cls(
            value["schema"],
            validate_portable_ref(value["commitment_id"], "commitment_id"),
            version,
            parent,
            validate_portable_ref(value["contract_ref"], "contract_ref"),
            validate_digest_ref(value["contract_digest"], "contract_digest"),
            validate_portable_ref(
                value["obligated_party_ref"], "obligated_party_ref"
            ),
            beneficiaries,
            value["action_class"],
            scope,
            due,
            value["status"],
            executions,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["beneficiary_party_refs"] = list(self.beneficiary_party_refs)
        value["scope"] = list(self.scope)
        value["execution_refs"] = list(self.execution_refs)
        value["due_or_review_at"] = self.due_or_review_at.to_dict()
        return value


@dataclass(frozen=True)
class AuthorityCandidate:
    schema: str
    candidate_id: str
    subject_entity_ref: str
    run_ref: str
    action_intent_ref: str
    action_intent_digest: str
    relation_refs: tuple[str, ...]
    contract_ref: str
    contract_digest: str
    active_lifecycle_head: str
    representation_grant_refs: tuple[str, ...]
    representation_grant_digests: tuple[str, ...]
    party_evidence_pin_refs: tuple[str, ...]
    party_evidence_set_digest: str
    requested_resource_scope: tuple[str, ...]
    requested_action_scope: tuple[str, ...]
    risk: str
    approval_mode: str
    continuity_precondition: str
    expires_at: NormalizedInstantEvidence
    clock_profile_id: str
    activation_time_ref: str
    activation_time_evidence_digest: str
    evaluator_profile_id: str
    evaluator_policy_version: str
    candidate_status: str
    reason_codes: tuple[str, ...]
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AuthorityCandidate":
        require_exact(value, CANDIDATE_FIELDS, "authority candidate")
        status = value["candidate_status"]
        if (
            value["schema"] != "arcp/authority-candidate/0.1"
            or value["risk"] not in {"R0", "R1"}
            or value["approval_mode"] != "all-named-parties"
            or value["continuity_precondition"] != "none"
            or status not in {"eligible", "blocked", "indeterminate"}
        ):
            raise RelationContractError("authority_candidate_invalid", value.get("candidate_id", ""))
        reasons = unique_strings(
            value["reason_codes"], "reason_codes", allow_empty=status == "eligible"
        )
        if (status == "eligible") != (not reasons):
            raise RelationContractError("authority_candidate_invalid", "reason_codes")
        grant_refs = unique_refs(
            value["representation_grant_refs"], "representation_grant_refs"
        )
        grant_digests = tuple(
            validate_digest_ref(item, "representation_grant_digests")
            for item in value["representation_grant_digests"]
        )
        if len(grant_refs) != len(grant_digests) or len(set(grant_digests)) != len(
            grant_digests
        ):
            raise RelationContractError("authority_candidate_invalid", "grant sets")
        party_refs = unique_refs(
            value["party_evidence_pin_refs"], "party_evidence_pin_refs"
        )
        expires = NormalizedInstantEvidence.from_dict(value["expires_at"])
        if value["clock_profile_id"] != expires.clock_profile_id:
            raise RelationContractError("authority_candidate_invalid", "clock profile")
        validate_content_digest(value, "authority candidate")
        return cls(
            value["schema"],
            validate_portable_ref(value["candidate_id"], "candidate_id"),
            validate_portable_ref(value["subject_entity_ref"], "subject_entity_ref"),
            validate_portable_ref(value["run_ref"], "run_ref"),
            validate_portable_ref(value["action_intent_ref"], "action_intent_ref"),
            validate_digest_ref(value["action_intent_digest"], "action_intent_digest"),
            unique_refs(value["relation_refs"], "relation_refs", allow_empty=True),
            validate_portable_ref(value["contract_ref"], "contract_ref"),
            validate_digest_ref(value["contract_digest"], "contract_digest"),
            validate_portable_ref(
                value["active_lifecycle_head"], "active_lifecycle_head"
            ),
            grant_refs,
            grant_digests,
            party_refs,
            validate_digest_ref(
                value["party_evidence_set_digest"], "party_evidence_set_digest"
            ),
            unique_strings(
                value["requested_resource_scope"], "requested_resource_scope"
            ),
            unique_strings(
                value["requested_action_scope"], "requested_action_scope"
            ),
            value["risk"],
            value["approval_mode"],
            value["continuity_precondition"],
            expires,
            validate_portable_ref(value["clock_profile_id"], "clock_profile_id"),
            validate_portable_ref(value["activation_time_ref"], "activation_time_ref"),
            validate_digest_ref(
                value["activation_time_evidence_digest"],
                "activation_time_evidence_digest",
            ),
            validate_portable_ref(value["evaluator_profile_id"], "evaluator_profile_id"),
            value["evaluator_policy_version"],
            status,
            reasons,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in (
            "relation_refs",
            "representation_grant_refs",
            "representation_grant_digests",
            "party_evidence_pin_refs",
            "requested_resource_scope",
            "requested_action_scope",
            "reason_codes",
        ):
            value[field] = list(value[field])
        value["expires_at"] = self.expires_at.to_dict()
        return value


@dataclass(frozen=True)
class AuthorityEvaluationReceipt:
    schema: str
    candidate_ref: str
    candidate_digest: str
    evaluator_profile_id: str
    evaluator_implementation_version: str
    evaluator_policy_version: str
    evaluated_evidence_set_digest: str
    authority_resolution: dict[str, Any]
    evaluated_at: NormalizedInstantEvidence
    receipt_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AuthorityEvaluationReceipt":
        require_exact(value, RECEIPT_FIELDS, "authority evaluation receipt")
        resolution = value["authority_resolution"]
        require_exact(resolution, RESOLUTION_FIELDS, "authority resolution")
        if (
            value["schema"] != "arcp/authority-evaluation-receipt/0.1"
            or resolution["schema"] != "arcp/authority-resolution/0.1"
            or resolution["status"]
            not in {"authorized", "approval-required", "multi-party-required", "denied"}
            or not isinstance(resolution["revocable"], bool)
            or resolution["continuity_precondition"]
            not in {"none", "verified-replica", "checkpoint", "migration", "separate-governance"}
        ):
            raise RelationContractError("authority_evaluation_invalid", "resolution")
        for field in (
            "resolution_id",
            "run_id",
            "action_id",
            "subject_entity_ref",
        ):
            validate_portable_ref(resolution[field], field)
        validate_digest_ref(resolution["action_hash"], "action_hash")
        unique_strings(resolution["sources"], "sources")
        unique_strings(resolution["resource_scope"], "resource_scope", allow_empty=True)
        unique_refs(resolution["relation_refs"], "relation_refs", allow_empty=True)
        unique_refs(resolution["contract_refs"], "contract_refs", allow_empty=True)
        NormalizedInstantEvidence.from_dict(resolution["expires_at"])
        expected = object_content_digest(value, "receipt_digest")
        if value["receipt_digest"] != expected:
            raise RelationContractError("receipt_digest_mismatch", "authority receipt")
        return cls(
            value["schema"],
            validate_portable_ref(value["candidate_ref"], "candidate_ref"),
            validate_digest_ref(value["candidate_digest"], "candidate_digest"),
            validate_portable_ref(value["evaluator_profile_id"], "evaluator_profile_id"),
            value["evaluator_implementation_version"],
            value["evaluator_policy_version"],
            validate_digest_ref(
                value["evaluated_evidence_set_digest"],
                "evaluated_evidence_set_digest",
            ),
            dict(resolution),
            NormalizedInstantEvidence.from_dict(value["evaluated_at"]),
            value["receipt_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "candidate_ref": self.candidate_ref,
            "candidate_digest": self.candidate_digest,
            "evaluator_profile_id": self.evaluator_profile_id,
            "evaluator_implementation_version": self.evaluator_implementation_version,
            "evaluator_policy_version": self.evaluator_policy_version,
            "evaluated_evidence_set_digest": self.evaluated_evidence_set_digest,
            "authority_resolution": dict(self.authority_resolution),
            "evaluated_at": self.evaluated_at.to_dict(),
            "receipt_digest": self.receipt_digest,
        }
