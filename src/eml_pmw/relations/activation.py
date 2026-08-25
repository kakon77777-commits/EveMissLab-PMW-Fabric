from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from eml_wake.canonical import canonical_bytes

from .authority import ral_pin_sufficient, validate_grant_authority
from .canonical import object_content_digest, profile_digest
from .models_authority import (
    AuthorityCandidate,
    AuthorityEvaluationReceipt,
    GrantAuthorityEvidence,
    PartyAcceptance,
    RepresentationGrant,
)
from .models_common import PartyEvidencePin
from .models_relation import ContractVersion
from .policy import ActivationPolicy
from .reducer import LifecycleProjection
from .temporal import NormalizedInstantEvidence, compare_instants


RISK_ORDER = {"R0": 0, "R1": 1}


@dataclass(frozen=True)
class ActivationInputs:
    contract: ContractVersion
    lifecycle_projection: LifecycleProjection
    acceptances: tuple[PartyAcceptance, ...]
    party_pins: tuple[PartyEvidencePin, ...]
    current_ledger_heads: Mapping[str, str]
    current_view_digests: Mapping[str, str]
    representation_grants: tuple[RepresentationGrant, ...]
    grant_authority_evidence: Mapping[str, GrantAuthorityEvidence]
    action_intent: dict[str, Any]
    now: NormalizedInstantEvidence
    policy: ActivationPolicy
    evaluator_profile_id: str
    evaluator_policy_version: str
    transition_authority_actions: tuple[str, ...]


@dataclass(frozen=True)
class ActivationDecision:
    status: str
    reason_codes: tuple[str, ...]
    acceptance_set_digest: str
    representation_set_digest: str
    party_evidence_set_digest: str


@dataclass(frozen=True)
class ReceiptCurrency:
    current: bool
    reason_code: str | None
    fresh_candidate_digest: str | None


def _set_digest(kind: str, digests) -> str:
    return profile_digest({"digests": sorted(digests), "kind": kind})


def _action_digest(action: Mapping[str, Any]) -> str:
    core = {key: item for key, item in action.items() if key != "action_intent_digest"}
    return "sha256:" + hashlib.sha256(canonical_bytes(core)).hexdigest()


def _time_state(
    start: NormalizedInstantEvidence,
    now: NormalizedInstantEvidence,
    end: NormalizedInstantEvidence,
) -> str:
    try:
        start_to_now = compare_instants(start, now)
        now_to_end = compare_instants(now, end)
    except Exception:
        return "indeterminate"
    if start_to_now == "after" or now_to_end == "after":
        return "outside"
    if start_to_now == "overlap" or now_to_end in {"overlap", "equal"}:
        return "indeterminate"
    return "inside"


def evaluate_activation(inputs: ActivationInputs) -> ActivationDecision:
    blocked: set[str] = set()
    indeterminate: set[str] = set()
    contract = inputs.contract
    projection = inputs.lifecycle_projection

    if (
        projection.contract_states.get(contract.contract_id) != "active"
        or contract.contract_id not in projection.active_heads
        or projection.active_head_digests.get(contract.contract_id)
        != contract.content_digest
        or contract.contract_id in projection.conflicts
    ):
        blocked.add("contract_active_head_invalid")

    if _action_digest(inputs.action_intent) != inputs.action_intent.get(
        "action_intent_digest"
    ):
        blocked.add("action_intent_digest_mismatch")

    action_spec_match = any(
        spec.subject_entity_ref == inputs.action_intent.get("subject_entity_ref")
        and tuple(spec.requested_resource_scope)
        == tuple(inputs.action_intent.get("requested_resource_scope", ()))
        and tuple(spec.requested_action_scope)
        == tuple(inputs.action_intent.get("requested_action_scope", ()))
        and spec.risk == inputs.action_intent.get("risk")
        for spec in contract.authority_candidate_specs
    )
    if not action_spec_match:
        blocked.add("action_intent_outside_contract")
    if (
        inputs.action_intent.get("risk") not in RISK_ORDER
        or RISK_ORDER.get(inputs.action_intent.get("risk"), 99)
        > RISK_ORDER[contract.risk_ceiling]
        or RISK_ORDER.get(inputs.action_intent.get("risk"), 99)
        > RISK_ORDER[inputs.policy.max_risk]
    ):
        blocked.add("activation_risk_exceeded")
    if "contract.activated" not in inputs.transition_authority_actions:
        blocked.add("activation_transition_authority_missing")

    time_state = _time_state(
        contract.effective_not_before, inputs.now, contract.expires_at
    )
    if time_state == "indeterminate":
        indeterminate.add("activation_time_indeterminate")
    elif time_state == "outside":
        blocked.add("activation_time_outside_contract")
    if (
        inputs.now.clock_profile_id not in inputs.policy.allowed_clock_profiles
        or inputs.now.uncertainty_ns > inputs.policy.max_clock_uncertainty_ns
    ):
        indeterminate.add("activation_time_indeterminate")

    required_parties = {
        term.party_ref for term in contract.party_terms if term.acceptance_required
    }
    current_acceptances = {
        item.party_ref: item
        for item in inputs.acceptances
        if item.target_kind == "contract"
        and item.target_id == contract.contract_id
        and item.target_version == contract.version
        and item.target_digest == contract.content_digest
    }
    if not required_parties <= set(current_acceptances):
        blocked.add("party_acceptance_missing")

    pins = {item.party_ref: item for item in inputs.party_pins}
    for party in sorted(required_parties):
        pin = pins.get(party)
        if pin is None or not ral_pin_sufficient(
            pin,
            current_ledger_head=inputs.current_ledger_heads.get(party, ""),
            current_view_digest=inputs.current_view_digests.get(party, ""),
        ):
            blocked.add("party_binding_inactive")

    grants = {item.principal_party_ref: item for item in inputs.representation_grants}
    forbidden_refs = {
        contract.contract_id,
        *(item for item in (contract.relation_version_ref,) if item is not None),
        *(item.representation_grant_id for item in inputs.representation_grants),
    }
    forbidden_digests = {
        contract.content_digest,
        *(item.content_digest for item in inputs.representation_grants),
    }
    for party in sorted(required_parties):
        grant = grants.get(party)
        if (
            grant is None
            or contract.contract_id not in grant.contract_scope
            or "contract.party_accepted" not in grant.allowed_lifecycle_actions
        ):
            blocked.add("representation_scope_mismatch")
            continue
        grant_time = _time_state(grant.valid_from, inputs.now, grant.expires_at)
        if grant_time == "indeterminate":
            indeterminate.add("representation_time_indeterminate")
        elif grant_time == "outside":
            blocked.add("representation_expired")
        try:
            validate_grant_authority(
                grant.grant_authority_ref,
                inputs.grant_authority_evidence,
                set(forbidden_refs),
                set(forbidden_digests),
            )
        except Exception as error:
            blocked.add(getattr(error, "code", "representation_authority_invalid"))
    actor_grant = grants.get(inputs.action_intent.get("subject_entity_ref"))
    if actor_grant is None or "contract.activated" not in actor_grant.allowed_lifecycle_actions:
        blocked.add("activation_representation_missing")

    acceptance_digest = _set_digest(
        "acceptance",
        (item.content_digest for item in current_acceptances.values()),
    )
    representation_digest = _set_digest(
        "representation",
        (item.content_digest for item in inputs.representation_grants),
    )
    pin_digest = _set_digest(
        "party-evidence", (item.content_digest for item in inputs.party_pins)
    )
    if indeterminate:
        return ActivationDecision(
            "indeterminate",
            tuple(sorted(indeterminate | blocked)),
            acceptance_digest,
            representation_digest,
            pin_digest,
        )
    if blocked:
        return ActivationDecision(
            "blocked",
            tuple(sorted(blocked)),
            acceptance_digest,
            representation_digest,
            pin_digest,
        )
    return ActivationDecision(
        "eligible", (), acceptance_digest, representation_digest, pin_digest
    )


def build_authority_candidate(
    inputs: ActivationInputs, decision: ActivationDecision
) -> AuthorityCandidate:
    contract = inputs.contract
    action = inputs.action_intent
    head = inputs.lifecycle_projection.active_heads.get(contract.contract_id, "")
    grant_pairs = sorted(
        (
            item.representation_grant_id,
            item.content_digest,
        )
        for item in inputs.representation_grants
    )
    pin_refs = sorted(item.content_digest for item in inputs.party_pins)
    candidate_seed = canonical_bytes(
        {
            "action": action.get("action_intent_digest"),
            "contract": contract.content_digest,
            "head": head,
        }
    )
    candidate_id = (
        "candidate:"
        + hashlib.sha256(candidate_seed).hexdigest()[:32]
    )
    value = {
        "schema": "arcp/authority-candidate/0.1",
        "candidate_id": candidate_id,
        "subject_entity_ref": action["subject_entity_ref"],
        "run_ref": action["run_ref"],
        "action_intent_ref": action["action_intent_ref"],
        "action_intent_digest": action["action_intent_digest"],
        "relation_refs": (
            [] if contract.relation_version_ref is None else [contract.relation_version_ref]
        ),
        "contract_ref": contract.contract_id,
        "contract_digest": contract.content_digest,
        "active_lifecycle_head": head,
        "representation_grant_refs": [item[0] for item in grant_pairs],
        "representation_grant_digests": [item[1] for item in grant_pairs],
        "party_evidence_pin_refs": pin_refs,
        "party_evidence_set_digest": decision.party_evidence_set_digest,
        "requested_resource_scope": list(action["requested_resource_scope"]),
        "requested_action_scope": list(action["requested_action_scope"]),
        "risk": action["risk"],
        "approval_mode": action["approval_mode"],
        "continuity_precondition": action["continuity_precondition"],
        "expires_at": contract.expires_at.to_dict(),
        "clock_profile_id": inputs.now.clock_profile_id,
        "activation_time_ref": inputs.now.instant_ref,
        "activation_time_evidence_digest": profile_digest(inputs.now.to_dict()),
        "evaluator_profile_id": inputs.evaluator_profile_id,
        "evaluator_policy_version": inputs.evaluator_policy_version,
        "candidate_status": decision.status,
        "reason_codes": list(decision.reason_codes),
        "content_digest": "",
    }
    value["content_digest"] = object_content_digest(value)
    return AuthorityCandidate.from_dict(value)


def recompute_candidate_from_current_state(inputs: ActivationInputs) -> AuthorityCandidate:
    decision = evaluate_activation(inputs)
    return build_authority_candidate(inputs, decision)


def receipt_is_current(
    receipt: AuthorityEvaluationReceipt, *, inputs: ActivationInputs
) -> ReceiptCurrency:
    fresh = recompute_candidate_from_current_state(inputs)
    if fresh.candidate_status != "eligible":
        return ReceiptCurrency(False, "authority_resolution_stale", fresh.content_digest)
    resolution = receipt.authority_resolution
    equal = (
        receipt.candidate_ref == fresh.candidate_id
        and receipt.candidate_digest == fresh.content_digest
        and receipt.evaluator_profile_id == fresh.evaluator_profile_id
        and receipt.evaluator_policy_version == fresh.evaluator_policy_version
        and receipt.evaluated_evidence_set_digest
        == fresh.party_evidence_set_digest
        and resolution["run_id"] == fresh.run_ref
        and resolution["action_id"] == fresh.action_intent_ref
        and resolution["action_hash"] == fresh.action_intent_digest
        and resolution["subject_entity_ref"] == fresh.subject_entity_ref
        and tuple(resolution["resource_scope"])
        == fresh.requested_resource_scope
        and tuple(resolution["relation_refs"]) == fresh.relation_refs
        and tuple(resolution["contract_refs"]) == (fresh.contract_ref,)
        and resolution["revocable"] is True
    )
    try:
        still_before_expiry = compare_instants(inputs.now, fresh.expires_at) == "before"
    except Exception:
        still_before_expiry = False
    if not equal or not still_before_expiry:
        return ReceiptCurrency(False, "authority_resolution_stale", fresh.content_digest)
    return ReceiptCurrency(True, None, fresh.content_digest)
