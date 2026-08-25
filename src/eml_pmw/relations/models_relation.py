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
    validate_version_parent,
)
from .policy import ActivationPolicy
from .references import validate_portable_ref
from .temporal import NormalizedInstantEvidence, compare_instants


EXIT_FIELDS = {
    "schema",
    "exit_path_id",
    "authorized_party_refs",
    "trigger_kind",
    "unilateral_allowed",
    "notice_duration_ms",
    "max_effective_delay_ms",
    "required_evidence_refs",
    "effects",
    "future_candidate_invalidation",
    "content_digest",
}
SURVIVAL_FIELDS = {
    "schema",
    "survival_clause_id",
    "class",
    "scope",
    "effective_after_termination",
    "expires_at",
    "future_authority",
    "content_digest",
}
TERMINATION_FIELDS = {
    "schema",
    "terminal_event_kinds",
    "terminal_precedence",
    "candidate_invalidation",
    "preserve_audit_history",
    "commitment_disposition",
    "allowed_survival_clause_refs",
    "content_digest",
}
RELATION_FIELDS = {
    "schema",
    "relation_id",
    "version",
    "parent_version_digest",
    "relation_class",
    "relation_type",
    "party_refs",
    "scope",
    "source_evidence_refs",
    "acceptance_rule",
    "not_claimed",
    "content_digest",
}
CONTRACT_FIELDS = {
    "schema",
    "contract_id",
    "version",
    "parent_version_digest",
    "relation_version_ref",
    "relation_version_digest",
    "party_terms",
    "scope",
    "commitment_specs",
    "authority_candidate_specs",
    "constraints",
    "risk_ceiling",
    "activation_policy_ref",
    "activation_policy_digest",
    "approval_mode",
    "effective_not_before",
    "expires_at",
    "review_at",
    "revocable",
    "redelegable",
    "termination_terms",
    "exit_paths",
    "survival_clauses",
    "succession_policy",
    "residence_impact",
    "continuity_impact",
    "continuity_precondition",
    "economic_terms_ref",
    "content_digest",
}
PARTY_TERM_FIELDS = {
    "party_ref",
    "role",
    "acceptance_required",
    "standing_entity",
    "representation_scope",
}
CANDIDATE_SPEC_FIELDS = {
    "subject_entity_ref",
    "requested_resource_scope",
    "requested_action_scope",
    "risk",
}
RISK_ORDER = {"R0": 0, "R1": 1}


@dataclass(frozen=True)
class ExitPath:
    schema: str
    exit_path_id: str
    authorized_party_refs: tuple[str, ...]
    trigger_kind: str
    unilateral_allowed: bool
    notice_duration_ms: int
    max_effective_delay_ms: int
    required_evidence_refs: tuple[str, ...]
    effects: str
    future_candidate_invalidation: str
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExitPath":
        require_exact(value, EXIT_FIELDS, "exit path")
        integers = (value["notice_duration_ms"], value["max_effective_delay_ms"])
        if (
            value["schema"] != "arcp/exit-path/0.1"
            or value["trigger_kind"]
            not in {
                "unilateral_notice",
                "mutual_acceptance",
                "breach",
                "expiry",
                "policy_event",
            }
            or not isinstance(value["unilateral_allowed"], bool)
            or any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in integers)
            or value["effects"]
            not in {"terminate_contract", "suspend_contract", "withdraw_acceptance"}
            or value["future_candidate_invalidation"] != "immediate"
        ):
            raise RelationContractError("exit_path_invalid", value.get("exit_path_id", ""))
        authorized = unique_refs(value["authorized_party_refs"], "authorized_party_refs")
        evidence = unique_refs(value["required_evidence_refs"], "required_evidence_refs")
        validate_content_digest(value, "exit path")
        return cls(
            value["schema"],
            validate_portable_ref(value["exit_path_id"], "exit_path_id"),
            authorized,
            value["trigger_kind"],
            value["unilateral_allowed"],
            value["notice_duration_ms"],
            value["max_effective_delay_ms"],
            evidence,
            value["effects"],
            value["future_candidate_invalidation"],
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["authorized_party_refs"] = list(self.authorized_party_refs)
        value["required_evidence_refs"] = list(self.required_evidence_refs)
        return value


@dataclass(frozen=True)
class SurvivalClause:
    schema: str
    survival_clause_id: str
    class_name: str
    scope: tuple[str, ...]
    effective_after_termination: bool
    expires_at: NormalizedInstantEvidence | None
    future_authority: bool
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "SurvivalClause":
        require_exact(value, SURVIVAL_FIELDS, "survival clause")
        if value["future_authority"] is not False:
            raise RelationContractError(
                "survival_future_authority_forbidden",
                value.get("survival_clause_id", ""),
            )
        if (
            value["schema"] != "arcp/survival-clause/0.1"
            or value["class"]
            not in {
                "audit_retention",
                "attribution",
                "confidentiality",
                "non_repudiation",
            }
            or value["effective_after_termination"] is not True
        ):
            raise RelationContractError("survival_clause_invalid", value.get("survival_clause_id", ""))
        expires = (
            None
            if value["expires_at"] is None
            else NormalizedInstantEvidence.from_dict(value["expires_at"])
        )
        scope = unique_refs(value["scope"], "scope")
        validate_content_digest(value, "survival clause")
        return cls(
            value["schema"],
            validate_portable_ref(
                value["survival_clause_id"], "survival_clause_id"
            ),
            value["class"],
            scope,
            True,
            expires,
            False,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "survival_clause_id": self.survival_clause_id,
            "class": self.class_name,
            "scope": list(self.scope),
            "effective_after_termination": self.effective_after_termination,
            "expires_at": None if self.expires_at is None else self.expires_at.to_dict(),
            "future_authority": self.future_authority,
            "content_digest": self.content_digest,
        }


@dataclass(frozen=True)
class TerminationTerms:
    schema: str
    terminal_event_kinds: tuple[str, ...]
    terminal_precedence: bool
    candidate_invalidation: str
    preserve_audit_history: bool
    commitment_disposition: str
    allowed_survival_clause_refs: tuple[str, ...]
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "TerminationTerms":
        require_exact(value, TERMINATION_FIELDS, "termination terms")
        if (
            value["schema"] != "arcp/termination-terms/0.1"
            or value["terminal_event_kinds"]
            != ["contract.expired", "contract.terminated"]
            or value["terminal_precedence"] is not True
            or value["candidate_invalidation"] != "immediate"
            or value["preserve_audit_history"] is not True
            or value["commitment_disposition"]
            not in {"terminate", "preserve_named_survival_clauses"}
        ):
            raise RelationContractError("termination_terms_invalid", "value")
        survival = unique_refs(
            value["allowed_survival_clause_refs"],
            "allowed_survival_clause_refs",
            allow_empty=value["commitment_disposition"] == "terminate",
        )
        validate_content_digest(value, "termination terms")
        return cls(
            value["schema"],
            tuple(value["terminal_event_kinds"]),
            True,
            "immediate",
            True,
            value["commitment_disposition"],
            survival,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["terminal_event_kinds"] = list(self.terminal_event_kinds)
        value["allowed_survival_clause_refs"] = list(
            self.allowed_survival_clause_refs
        )
        return value


@dataclass(frozen=True)
class RelationVersion:
    schema: str
    relation_id: str
    version: int
    parent_version_digest: str | None
    relation_class: str
    relation_type: str
    party_refs: tuple[str, ...]
    scope: tuple[str, ...]
    source_evidence_refs: tuple[str, ...]
    acceptance_rule: str
    not_claimed: tuple[str, ...]
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RelationVersion":
        require_exact(value, RELATION_FIELDS, "relation version")
        version, parent = validate_version_parent(
            value["version"], value["parent_version_digest"], "relation"
        )
        relation_class = value["relation_class"]
        acceptance_rule = value["acceptance_rule"]
        if (
            value["schema"] != "arcp/relation-version/0.1"
            or relation_class not in {"descriptive", "consensual", "authority-bearing"}
            or not isinstance(value["relation_type"], str)
            or not value["relation_type"]
            or acceptance_rule not in {"none", "all-named-parties"}
            or (relation_class == "descriptive" and acceptance_rule != "none")
            or (relation_class != "descriptive" and acceptance_rule != "all-named-parties")
        ):
            raise RelationContractError("relation_contract_invalid", value.get("relation_id", ""))
        parties = unique_refs(value["party_refs"], "party_refs")
        if len(parties) < 2:
            raise RelationContractError("relation_contract_invalid", "party_refs")
        scope = unique_refs(value["scope"], "scope")
        evidence = unique_refs(value["source_evidence_refs"], "source_evidence_refs")
        not_claimed = unique_strings(
            value["not_claimed"], "not_claimed", allow_empty=True
        )
        if "relation_grants_authority" not in not_claimed:
            raise RelationContractError(
                "relation_authority_nonclaim_missing", value["relation_id"]
            )
        validate_content_digest(value, "relation version")
        return cls(
            value["schema"],
            validate_portable_ref(value["relation_id"], "relation_id"),
            version,
            parent,
            relation_class,
            value["relation_type"],
            parties,
            scope,
            evidence,
            acceptance_rule,
            not_claimed,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in ("party_refs", "scope", "source_evidence_refs", "not_claimed"):
            value[field] = list(value[field])
        return value


@dataclass(frozen=True)
class PartyTerm:
    party_ref: str
    role: str
    acceptance_required: bool
    standing_entity: bool
    representation_scope: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "PartyTerm":
        require_exact(value, PARTY_TERM_FIELDS, "party term")
        if (
            not isinstance(value["role"], str)
            or not value["role"]
            or not isinstance(value["acceptance_required"], bool)
            or not isinstance(value["standing_entity"], bool)
        ):
            raise RelationContractError("party_term_invalid", str(value))
        return cls(
            validate_portable_ref(value["party_ref"], "party_ref"),
            value["role"],
            value["acceptance_required"],
            value["standing_entity"],
            unique_strings(value["representation_scope"], "representation_scope"),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["representation_scope"] = list(self.representation_scope)
        return value


@dataclass(frozen=True)
class AuthorityCandidateSpec:
    subject_entity_ref: str
    requested_resource_scope: tuple[str, ...]
    requested_action_scope: tuple[str, ...]
    risk: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AuthorityCandidateSpec":
        require_exact(value, CANDIDATE_SPEC_FIELDS, "authority candidate spec")
        if value["risk"] not in RISK_ORDER:
            raise RelationContractError("contract_v1_boundary_invalid", "candidate risk")
        return cls(
            validate_portable_ref(value["subject_entity_ref"], "subject_entity_ref"),
            unique_strings(value["requested_resource_scope"], "requested_resource_scope"),
            unique_strings(value["requested_action_scope"], "requested_action_scope"),
            value["risk"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["requested_resource_scope"] = list(self.requested_resource_scope)
        value["requested_action_scope"] = list(self.requested_action_scope)
        return value


@dataclass(frozen=True)
class ContractVersion:
    schema: str
    contract_id: str
    version: int
    parent_version_digest: str | None
    relation_version_ref: str | None
    relation_version_digest: str | None
    party_terms: tuple[PartyTerm, ...]
    scope: tuple[str, ...]
    commitment_specs: tuple[dict[str, Any], ...]
    authority_candidate_specs: tuple[AuthorityCandidateSpec, ...]
    constraints: tuple[str, ...]
    risk_ceiling: str
    activation_policy_ref: str
    activation_policy_digest: str
    approval_mode: str
    effective_not_before: NormalizedInstantEvidence
    expires_at: NormalizedInstantEvidence
    review_at: NormalizedInstantEvidence | None
    revocable: bool
    redelegable: bool
    termination_terms: TerminationTerms
    exit_paths: tuple[ExitPath, ...]
    survival_clauses: tuple[SurvivalClause, ...]
    succession_policy: str
    residence_impact: str
    continuity_impact: str
    continuity_precondition: str
    economic_terms_ref: None
    content_digest: str

    @classmethod
    def from_dict(
        cls, value: dict[str, Any], *, policy: ActivationPolicy
    ) -> "ContractVersion":
        require_exact(value, CONTRACT_FIELDS, "contract version")
        version, parent = validate_version_parent(
            value["version"], value["parent_version_digest"], "contract"
        )
        relation_ref = value["relation_version_ref"]
        relation_digest = value["relation_version_digest"]
        if (relation_ref is None) != (relation_digest is None):
            raise RelationContractError(
                "relation_version_pin_incomplete", value.get("contract_id", "")
            )
        if relation_ref is not None:
            relation_ref = validate_portable_ref(relation_ref, "relation_version_ref")
            relation_digest = validate_digest_ref(
                relation_digest, "relation_version_digest"
            )
        if (
            value["activation_policy_ref"] != policy.policy_id
            or value["activation_policy_digest"] != policy.content_digest
        ):
            raise RelationContractError(
                "activation_policy_digest_mismatch", value.get("contract_id", "")
            )
        if (
            value["schema"] != "arcp/contract-version/0.1"
            or value["risk_ceiling"] not in RISK_ORDER
            or RISK_ORDER[value["risk_ceiling"]] > RISK_ORDER[policy.max_risk]
            or value["approval_mode"] != "all-named-parties"
            or value["revocable"] is not True
            or value["redelegable"] is not False
            or value["succession_policy"] != "explicit_acceptance_only"
            or value["residence_impact"] != "none"
            or value["continuity_impact"] != "none"
            or value["continuity_precondition"] != "none"
            or value["economic_terms_ref"] is not None
        ):
            raise RelationContractError(
                "contract_v1_boundary_invalid", value.get("contract_id", "")
            )
        terms = tuple(PartyTerm.from_dict(item) for item in value["party_terms"])
        if len(terms) < 2 or len({item.party_ref for item in terms}) != len(terms):
            raise RelationContractError("party_term_invalid", "party_terms")
        scope = unique_strings(value["scope"], "scope")
        if not isinstance(value["commitment_specs"], list):
            raise RelationContractError("field_type_invalid", "commitment_specs")
        commitment_specs = tuple(value["commitment_specs"])
        if any(not isinstance(item, dict) for item in commitment_specs):
            raise RelationContractError("field_type_invalid", "commitment_specs")
        candidate_specs = tuple(
            AuthorityCandidateSpec.from_dict(item)
            for item in value["authority_candidate_specs"]
        )
        if any(RISK_ORDER[item.risk] > RISK_ORDER[value["risk_ceiling"]] for item in candidate_specs):
            raise RelationContractError("contract_v1_boundary_invalid", "candidate risk")
        constraints = unique_strings(value["constraints"], "constraints", allow_empty=True)
        effective = NormalizedInstantEvidence.from_dict(value["effective_not_before"])
        expires = NormalizedInstantEvidence.from_dict(value["expires_at"])
        if (
            effective.clock_profile_id not in policy.allowed_clock_profiles
            or expires.clock_profile_id not in policy.allowed_clock_profiles
            or effective.uncertainty_ns > policy.max_clock_uncertainty_ns
            or expires.uncertainty_ns > policy.max_clock_uncertainty_ns
            or compare_instants(effective, expires) != "before"
            or expires.upper_ns - effective.lower_ns
            > policy.max_activation_duration_ms * 1_000_000
        ):
            raise RelationContractError("contract_time_invalid", value["contract_id"])
        review = (
            None
            if value["review_at"] is None
            else NormalizedInstantEvidence.from_dict(value["review_at"])
        )
        termination = TerminationTerms.from_dict(value["termination_terms"])
        exits = tuple(ExitPath.from_dict(item) for item in value["exit_paths"])
        survivals = tuple(
            SurvivalClause.from_dict(item) for item in value["survival_clauses"]
        )
        survival_ids = {item.survival_clause_id for item in survivals}
        if not set(termination.allowed_survival_clause_refs) <= survival_ids:
            raise RelationContractError("termination_terms_invalid", "survival refs")
        for term in (item for item in terms if item.standing_entity):
            if not any(
                term.party_ref in exit_path.authorized_party_refs
                and exit_path.trigger_kind == "unilateral_notice"
                and exit_path.unilateral_allowed
                and exit_path.notice_duration_ms <= policy.max_exit_notice_ms
                for exit_path in exits
            ):
                raise RelationContractError("activation_exit_missing", term.party_ref)
        validate_content_digest(value, "contract version")
        return cls(
            value["schema"],
            validate_portable_ref(value["contract_id"], "contract_id"),
            version,
            parent,
            relation_ref,
            relation_digest,
            terms,
            scope,
            commitment_specs,
            candidate_specs,
            constraints,
            value["risk_ceiling"],
            value["activation_policy_ref"],
            value["activation_policy_digest"],
            value["approval_mode"],
            effective,
            expires,
            review,
            True,
            False,
            termination,
            exits,
            survivals,
            value["succession_policy"],
            "none",
            "none",
            "none",
            None,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "contract_id": self.contract_id,
            "version": self.version,
            "parent_version_digest": self.parent_version_digest,
            "relation_version_ref": self.relation_version_ref,
            "relation_version_digest": self.relation_version_digest,
            "party_terms": [item.to_dict() for item in self.party_terms],
            "scope": list(self.scope),
            "commitment_specs": list(self.commitment_specs),
            "authority_candidate_specs": [
                item.to_dict() for item in self.authority_candidate_specs
            ],
            "constraints": list(self.constraints),
            "risk_ceiling": self.risk_ceiling,
            "activation_policy_ref": self.activation_policy_ref,
            "activation_policy_digest": self.activation_policy_digest,
            "approval_mode": self.approval_mode,
            "effective_not_before": self.effective_not_before.to_dict(),
            "expires_at": self.expires_at.to_dict(),
            "review_at": None if self.review_at is None else self.review_at.to_dict(),
            "revocable": self.revocable,
            "redelegable": self.redelegable,
            "termination_terms": self.termination_terms.to_dict(),
            "exit_paths": [item.to_dict() for item in self.exit_paths],
            "survival_clauses": [item.to_dict() for item in self.survival_clauses],
            "succession_policy": self.succession_policy,
            "residence_impact": self.residence_impact,
            "continuity_impact": self.continuity_impact,
            "continuity_precondition": self.continuity_precondition,
            "economic_terms_ref": self.economic_terms_ref,
            "content_digest": self.content_digest,
        }
