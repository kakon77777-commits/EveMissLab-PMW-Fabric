from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Protocol, runtime_checkable

from .canonical import object_content_digest
from .errors import RelationContractError
from .models_authority import AuthorityCandidate, AuthorityEvaluationReceipt
from .references import validate_portable_ref
from .temporal import NormalizedInstantEvidence, compare_instants


RISK_ORDER = {"R0": 0, "R1": 1}
EVALUATOR_IMPLEMENTATION_VERSION = "eml-pmw-deterministic-arcp-evaluator/0.1"


class AuthorityEvaluatorUnavailable(RuntimeError):
    pass


class AuthorityEvaluatorIndeterminate(RuntimeError):
    def __init__(self, reason_codes: tuple[str, ...]):
        if not reason_codes or len(reason_codes) != len(set(reason_codes)):
            raise ValueError("indeterminate evaluator reasons must be unique")
        self.reason_codes = tuple(sorted(reason_codes))
        super().__init__(",".join(self.reason_codes))


@runtime_checkable
class AuthorityEvaluatorPort(Protocol):
    def evaluate(
        self,
        candidate: AuthorityCandidate,
        now: NormalizedInstantEvidence,
    ) -> AuthorityEvaluationReceipt: ...


@dataclass(frozen=True)
class EvaluationDecision:
    status: str
    reason_codes: tuple[str, ...]
    receipt: AuthorityEvaluationReceipt | None


@dataclass(frozen=True)
class OfflineEvaluatorGrant:
    grant_ref: str
    subject_entity_ref: str
    resource_scope: tuple[str, ...]
    action_scope: tuple[str, ...]
    max_risk: str
    named_party_approval_status: str
    containment_status: str
    allowed_continuity_preconditions: tuple[str, ...]

    def __post_init__(self) -> None:
        validate_portable_ref(self.grant_ref, "grant_ref")
        validate_portable_ref(self.subject_entity_ref, "subject_entity_ref")
        sequences = {
            "resource_scope": self.resource_scope,
            "action_scope": self.action_scope,
            "allowed_continuity_preconditions": self.allowed_continuity_preconditions,
        }
        for field, values in sequences.items():
            if (
                not isinstance(values, tuple)
                or not values
                or len(values) != len(set(values))
                or any(not isinstance(value, str) or not value for value in values)
            ):
                raise RelationContractError("evaluator_grant_invalid", field)
        if (
            self.max_risk not in RISK_ORDER
            or self.named_party_approval_status
            not in {"verified", "missing", "rejected"}
            or self.containment_status not in {"active", "blocked", "unmeasured"}
        ):
            raise RelationContractError("evaluator_grant_invalid", self.grant_ref)


def _receipt_for(
    candidate: AuthorityCandidate,
    now: NormalizedInstantEvidence,
    *,
    policy_version: str,
    status: str,
    source: str,
) -> AuthorityEvaluationReceipt:
    resolution_id = (
        "arcp:authority:"
        + hashlib.sha256(candidate.content_digest.encode("utf-8")).hexdigest()[:32]
    )
    sources = ["contract-authorized"] if status == "authorized" else [source]
    value = {
        "schema": "arcp/authority-evaluation-receipt/0.1",
        "candidate_ref": candidate.candidate_id,
        "candidate_digest": candidate.content_digest,
        "evaluator_profile_id": candidate.evaluator_profile_id,
        "evaluator_implementation_version": EVALUATOR_IMPLEMENTATION_VERSION,
        "evaluator_policy_version": policy_version,
        "evaluated_evidence_set_digest": candidate.party_evidence_set_digest,
        "authority_resolution": {
            "schema": "arcp/authority-resolution/0.1",
            "resolution_id": resolution_id,
            "run_id": candidate.run_ref,
            "action_id": candidate.action_intent_ref,
            "action_hash": candidate.action_intent_digest,
            "status": status,
            "sources": sources,
            "subject_entity_ref": candidate.subject_entity_ref,
            "resource_scope": list(candidate.requested_resource_scope),
            "relation_refs": list(candidate.relation_refs),
            "contract_refs": [candidate.contract_ref],
            "revocable": True,
            "expires_at": candidate.expires_at.to_dict(),
            "continuity_precondition": candidate.continuity_precondition,
        },
        "evaluated_at": now.to_dict(),
        "receipt_digest": "",
    }
    value["receipt_digest"] = object_content_digest(value, "receipt_digest")
    return AuthorityEvaluationReceipt.from_dict(value)


class DeterministicAuthorityEvaluator:
    def __init__(
        self,
        policy_version: str,
        grants: tuple[OfflineEvaluatorGrant, ...],
    ):
        if not isinstance(policy_version, str) or not policy_version:
            raise RelationContractError("evaluator_policy_invalid", "policy_version")
        if (
            not isinstance(grants, tuple)
            or any(not isinstance(item, OfflineEvaluatorGrant) for item in grants)
            or len({item.grant_ref for item in grants}) != len(grants)
        ):
            raise RelationContractError("evaluator_grant_invalid", "grants")
        self.policy_version = policy_version
        self.grants = tuple(sorted(grants, key=lambda item: item.grant_ref))

    def evaluate(
        self,
        candidate: AuthorityCandidate,
        now: NormalizedInstantEvidence,
    ) -> AuthorityEvaluationReceipt:
        if not isinstance(candidate, AuthorityCandidate):
            raise RelationContractError("authority_candidate_invalid", "candidate")
        if not isinstance(now, NormalizedInstantEvidence):
            raise RelationContractError("temporal_evidence_invalid", "now")
        if candidate.candidate_status != "eligible":
            raise RelationContractError(
                "authority_candidate_not_eligible", candidate.candidate_id
            )
        if candidate.evaluator_policy_version != self.policy_version:
            raise RelationContractError(
                "evaluator_policy_version_mismatch", candidate.candidate_id
            )
        if now.clock_profile_id != candidate.clock_profile_id:
            raise AuthorityEvaluatorIndeterminate(("evaluator_clock_profile_mismatch",))
        try:
            temporal = compare_instants(now, candidate.expires_at)
        except RelationContractError as error:
            if error.code == "temporal_evidence_insufficient":
                raise AuthorityEvaluatorIndeterminate((error.code,)) from error
            raise
        if temporal == "overlap":
            raise AuthorityEvaluatorIndeterminate(("candidate_expiry_indeterminate",))
        if temporal in {"equal", "after"}:
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="denied",
                source="fake-policy:candidate-expired",
            )
        if candidate.continuity_precondition != "none":
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="denied",
                source="fake-policy:continuity-precondition-unsupported",
            )

        matching = [
            item
            for item in self.grants
            if item.subject_entity_ref == candidate.subject_entity_ref
        ]
        if not matching:
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="approval-required",
                source="fake-policy:grant-missing",
            )
        if len(matching) != 1:
            raise AuthorityEvaluatorIndeterminate(("evaluator_grant_ambiguous",))
        grant = matching[0]
        if (
            not set(candidate.requested_resource_scope) <= set(grant.resource_scope)
            or not set(candidate.requested_action_scope) <= set(grant.action_scope)
        ):
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="denied",
                source="fake-policy:scope-not-covered",
            )
        if RISK_ORDER[candidate.risk] > RISK_ORDER[grant.max_risk]:
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="denied",
                source="fake-policy:risk-exceeded",
            )
        if grant.named_party_approval_status == "missing":
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="multi-party-required",
                source="fake-policy:named-party-approval-missing",
            )
        if grant.named_party_approval_status == "rejected":
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="denied",
                source="fake-policy:named-party-approval-rejected",
            )
        if grant.containment_status == "blocked":
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="denied",
                source="fake-policy:containment-blocked",
            )
        if grant.containment_status == "unmeasured":
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="approval-required",
                source="fake-policy:containment-unmeasured",
            )
        if candidate.continuity_precondition not in grant.allowed_continuity_preconditions:
            return _receipt_for(
                candidate,
                now,
                policy_version=self.policy_version,
                status="denied",
                source="fake-policy:continuity-precondition-unsupported",
            )
        return _receipt_for(
            candidate,
            now,
            policy_version=self.policy_version,
            status="authorized",
            source="contract-authorized",
        )


def _validate_receipt_binding(
    receipt: AuthorityEvaluationReceipt, candidate: AuthorityCandidate
) -> None:
    resolution = receipt.authority_resolution
    if (
        receipt.candidate_ref != candidate.candidate_id
        or receipt.candidate_digest != candidate.content_digest
        or receipt.evaluator_profile_id != candidate.evaluator_profile_id
        or receipt.evaluator_policy_version != candidate.evaluator_policy_version
        or receipt.evaluated_evidence_set_digest
        != candidate.party_evidence_set_digest
        or resolution["run_id"] != candidate.run_ref
        or resolution["action_id"] != candidate.action_intent_ref
        or resolution["action_hash"] != candidate.action_intent_digest
        or resolution["subject_entity_ref"] != candidate.subject_entity_ref
        or tuple(resolution["resource_scope"])
        != candidate.requested_resource_scope
        or tuple(resolution["relation_refs"]) != candidate.relation_refs
        or tuple(resolution["contract_refs"]) != (candidate.contract_ref,)
        or resolution["expires_at"] != candidate.expires_at.to_dict()
        or resolution["continuity_precondition"]
        != candidate.continuity_precondition
        or resolution["revocable"] is not True
    ):
        raise RelationContractError(
            "authority_evaluation_binding_mismatch", candidate.candidate_id
        )


def evaluate_with_port(
    evaluator: AuthorityEvaluatorPort,
    candidate: AuthorityCandidate,
    now: NormalizedInstantEvidence,
) -> EvaluationDecision:
    if candidate.candidate_status != "eligible":
        raise RelationContractError(
            "authority_candidate_not_eligible", candidate.candidate_id
        )
    try:
        receipt = evaluator.evaluate(candidate, now)
    except AuthorityEvaluatorUnavailable:
        return EvaluationDecision(
            "indeterminate", ("authority_evaluator_unavailable",), None
        )
    except AuthorityEvaluatorIndeterminate as error:
        return EvaluationDecision("indeterminate", error.reason_codes, None)
    if not isinstance(receipt, AuthorityEvaluationReceipt):
        raise RelationContractError(
            "authority_evaluation_invalid", candidate.candidate_id
        )
    _validate_receipt_binding(receipt, candidate)
    return EvaluationDecision(
        str(receipt.authority_resolution["status"]), (), receipt
    )
