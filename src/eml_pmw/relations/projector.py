from __future__ import annotations

from collections import defaultdict
from typing import Any

from eml_wake.canonical import canonical_bytes, loads_strict

from .canonical import profile_digest
from .errors import RelationContractError
from .reducer import LifecycleProjection, reduce_events


PROJECTION_SCHEMA = "arcp/relation-contract-projection/0.1"
PROJECTABLE_STORE_STATUSES = {
    "empty",
    "internally_consistent",
    "checkpoint_verified",
}
PROJECTION_NONCLAIMS = (
    "authority_evaluation_is_execution",
    "contract_activation_is_execution",
    "delivery_is_acceptance",
    "projection_is_capability",
    "projection_is_identity_continuity",
)


def projection_digest(projection_value: dict[str, Any]) -> str:
    """Digest a projection without allowing the digest to include itself."""

    core = {
        key: item
        for key, item in projection_value.items()
        if key != "projection_digest"
    }
    return profile_digest(core)


def _require_projectable(store: Any) -> None:
    verification = store.verify()
    status = getattr(verification, "status", None)
    if status not in PROJECTABLE_STORE_STATUSES:
        raise RelationContractError("store_not_projectable", str(status))


def _objects_with_schema(
    objects: dict[str, dict[str, Any]], schema: str
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (digest, value)
        for digest, value in sorted(objects.items())
        if value.get("schema") == schema
    ]


def _contract_projection_state(
    contract_id: str, lifecycle: LifecycleProjection
) -> str:
    raw = lifecycle.contract_states.get(contract_id)
    if contract_id in lifecycle.conflicts or raw == "conflicted_heads":
        return "conflicted_heads"
    if raw in {"terminated", "expired"}:
        return str(raw)
    if raw in {"blocked", "indeterminate"}:
        return str(raw)
    if contract_id in lifecycle.active_heads:
        return "single_head_active"
    return "single_head_inactive"


def _build_projection(
    events: tuple[Any, ...],
    objects: dict[str, dict[str, Any]],
    lifecycle: LifecycleProjection,
) -> dict[str, Any]:
    relation_versions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    relation_id_by_digest: dict[str, str] = {}
    for digest, value in _objects_with_schema(objects, "arcp/relation-version/0.1"):
        relation_id = str(value["relation_id"])
        relation_id_by_digest[digest] = relation_id
        relation_versions[relation_id].append(
            {
                "version": value["version"],
                "content_digest": digest,
                "parent_version_digest": value["parent_version_digest"],
                "relation_class": value["relation_class"],
                "acceptance_rule": value["acceptance_rule"],
            }
        )

    contract_versions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    reverse_contracts: dict[str, set[str]] = defaultdict(set)
    for digest, value in _objects_with_schema(objects, "arcp/contract-version/0.1"):
        contract_id = str(value["contract_id"])
        contract_versions[contract_id].append(
            {
                "version": value["version"],
                "content_digest": digest,
                "parent_version_digest": value["parent_version_digest"],
                "relation_version_ref": value["relation_version_ref"],
                "relation_version_digest": value["relation_version_digest"],
            }
        )
        relation_digest = value.get("relation_version_digest")
        if relation_digest in relation_id_by_digest:
            reverse_contracts[relation_id_by_digest[relation_digest]].add(contract_id)

    relations = {
        relation_id: {
            "state": lifecycle.relation_states.get(relation_id, "unobserved"),
            "versions": sorted(
                versions,
                key=lambda item: (item["version"], item["content_digest"]),
            ),
            "derived_contract_refs": sorted(reverse_contracts[relation_id]),
        }
        for relation_id, versions in sorted(relation_versions.items())
    }
    contracts = {
        contract_id: {
            "state": _contract_projection_state(contract_id, lifecycle),
            "lifecycle_state": lifecycle.contract_states.get(
                contract_id, "unobserved"
            ),
            "active_lifecycle_head": lifecycle.active_heads.get(contract_id),
            "active_contract_digest": lifecycle.active_head_digests.get(contract_id),
            "versions": sorted(
                versions,
                key=lambda item: (item["version"], item["content_digest"]),
            ),
            "execution_status": "not_observed",
        }
        for contract_id, versions in sorted(contract_versions.items())
    }

    representation_grants = {}
    for digest, value in _objects_with_schema(
        objects, "arcp/representation-grant/0.1"
    ):
        identifier = str(value["representation_grant_id"])
        representation_grants[identifier] = {
            "status": lifecycle.representation_states.get(identifier, "unobserved"),
            "content_digest": digest,
            "state_head": lifecycle.representation_state_heads.get(identifier),
            "principal_party_ref": value["principal_party_ref"],
            "representative_ref": value["representative_ref"],
        }

    acceptances = {}
    for digest, value in _objects_with_schema(objects, "arcp/party-acceptance/0.1"):
        active_parties = set(lifecycle.acceptances.get(value["target_digest"], ()))
        acceptances[str(value["acceptance_id"])] = {
            "status": (
                "accepted" if value["party_ref"] in active_parties else "inactive"
            ),
            "content_digest": digest,
            "party_ref": value["party_ref"],
            "target_kind": value["target_kind"],
            "target_id": value["target_id"],
            "target_digest": value["target_digest"],
            "acceptance_evidence_root_refs": sorted(
                value["acceptance_evidence_root_refs"]
            ),
        }

    commitment_versions: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for digest, value in _objects_with_schema(objects, "arcp/commitment/0.1"):
        commitment_versions[str(value["commitment_id"])].append(
            {
                "version": value["version"],
                "content_digest": digest,
                "parent_version_digest": value["parent_version_digest"],
                "contract_ref": value["contract_ref"],
                "declared_status": value["status"],
            }
        )
    commitments = {
        identifier: {
            "status": lifecycle.commitment_states.get(identifier, "unobserved"),
            "versions": sorted(
                versions,
                key=lambda item: (item["version"], item["content_digest"]),
            ),
        }
        for identifier, versions in sorted(commitment_versions.items())
    }

    authority_candidates = {}
    for digest, value in _objects_with_schema(objects, "arcp/authority-candidate/0.1"):
        authority_candidates[digest] = {
            "candidate_id": value["candidate_id"],
            "projection_state": lifecycle.candidate_states.get(
                digest, "unobserved"
            ),
            "candidate_status": value["candidate_status"],
            "reason_codes": sorted(value["reason_codes"]),
            "contract_ref": value["contract_ref"],
            "contract_digest": value["contract_digest"],
            "active_lifecycle_head": value["active_lifecycle_head"],
            "representation_grant_refs": sorted(
                value["representation_grant_refs"]
            ),
            "party_evidence_pin_refs": sorted(value["party_evidence_pin_refs"]),
            "party_evidence_set_digest": value["party_evidence_set_digest"],
            "evaluator_profile_id": value["evaluator_profile_id"],
            "evaluator_policy_version": value["evaluator_policy_version"],
        }

    authority_evaluations = {}
    for digest, value in _objects_with_schema(
        objects, "arcp/authority-evaluation-receipt/0.1"
    ):
        authority_evaluations[digest] = {
            "projection_state": lifecycle.evaluation_states.get(
                digest, "unobserved"
            ),
            "candidate_ref": value["candidate_ref"],
            "candidate_digest": value["candidate_digest"],
            "evaluator_profile_id": value["evaluator_profile_id"],
            "evaluator_implementation_version": value[
                "evaluator_implementation_version"
            ],
            "evaluator_policy_version": value["evaluator_policy_version"],
            "resolution_status": value["authority_resolution"]["status"],
            "receipt_currency": "recorded_not_revalidated",
        }

    value = {
        "schema": PROJECTION_SCHEMA,
        "projection_digest": "",
        "source_event_digests": sorted(event.event_digest for event in events),
        "relations": relations,
        "contracts": contracts,
        "representation_grants": dict(sorted(representation_grants.items())),
        "acceptances": dict(sorted(acceptances.items())),
        "commitments": commitments,
        "authority_candidates": dict(sorted(authority_candidates.items())),
        "authority_evaluations": dict(sorted(authority_evaluations.items())),
        "conflicts": sorted(lifecycle.conflicts),
        "invalidated_candidate_digests": sorted(
            lifecycle.invalidated_candidate_digests
        ),
        "not_claimed": list(PROJECTION_NONCLAIMS),
    }
    value["projection_digest"] = projection_digest(value)
    return value


def rebuild_projection(store: Any) -> bytes:
    """Rebuild deterministic derived state from an internally consistent store."""

    _require_projectable(store)
    events = tuple(store.events())
    objects = store.objects_by_digest()
    lifecycle = reduce_events(events, objects)
    return canonical_bytes(_build_projection(events, objects, lifecycle))


def explain_subject(store: Any, subject_ref: str) -> dict[str, Any]:
    """Explain evidence layers without collapsing them into authorization."""

    projection = loads_strict(rebuild_projection(store))
    if subject_ref in projection["contracts"]:
        subject_kind = "contract"
        subject = projection["contracts"][subject_ref]
    elif subject_ref in projection["relations"]:
        subject_kind = "relation"
        subject = projection["relations"][subject_ref]
    else:
        raise RelationContractError("subject_not_found", subject_ref)

    events = tuple(store.events())
    active_head = (
        subject.get("active_lifecycle_head") if subject_kind == "contract" else None
    )
    active_event = next(
        (event for event in events if event.event_id == active_head), None
    )
    candidate_items = [
        (digest, value)
        for digest, value in projection["authority_candidates"].items()
        if value["contract_ref"] == subject_ref
        and value["projection_state"] != "invalidated"
    ]
    candidate_digest = candidate_items[0][0] if len(candidate_items) == 1 else None
    candidate = candidate_items[0][1] if len(candidate_items) == 1 else None
    receipt_items = [
        (digest, value)
        for digest, value in projection["authority_evaluations"].items()
        if candidate_digest is not None and value["candidate_digest"] == candidate_digest
    ]
    receipt_digest = receipt_items[0][0] if len(receipt_items) == 1 else None
    receipt = receipt_items[0][1] if len(receipt_items) == 1 else None

    acceptance_roots = sorted(
        {
            root
            for value in projection["acceptances"].values()
            if value["target_id"] == subject_ref and value["status"] == "accepted"
            for root in value["acceptance_evidence_root_refs"]
        }
    )
    representation_validity = {
        identifier: projection["representation_grants"].get(
            identifier, {"status": "unmeasured"}
        )["status"]
        for identifier in ([] if candidate is None else candidate["representation_grant_refs"])
    }
    return {
        "schema": "arcp/relation-contract-explain/0.1",
        "subject_ref": subject_ref,
        "subject_kind": subject_kind,
        "lifecycle_state": subject["state"],
        "active_lifecycle_head": active_head,
        "source_event_digests": projection["source_event_digests"],
        "acceptance_set_digest": (
            None if active_event is None else active_event.acceptance_set_digest
        ),
        "acceptance_evidence_root_refs": acceptance_roots,
        "representation_set_digest": (
            None if active_event is None else active_event.representation_set_digest
        ),
        "representation_validity": representation_validity,
        "party_evidence_set_digest": (
            None if candidate is None else candidate["party_evidence_set_digest"]
        ),
        "current_party_pin_refs": (
            [] if candidate is None else candidate["party_evidence_pin_refs"]
        ),
        "authority_candidate_digest": candidate_digest,
        "candidate_status": None if candidate is None else candidate["candidate_status"],
        "activation_reason_codes": (
            [] if candidate is None else candidate["reason_codes"]
        ),
        "authority_evaluation_receipt_digest": receipt_digest,
        "evaluator_profile_id": (
            None if receipt is None else receipt["evaluator_profile_id"]
        ),
        "evaluator_implementation_version": (
            None if receipt is None else receipt["evaluator_implementation_version"]
        ),
        "evaluator_policy_version": (
            None if receipt is None else receipt["evaluator_policy_version"]
        ),
        "receipt_currency": None if receipt is None else receipt["receipt_currency"],
        "execution_status": "not_observed",
        "not_claimed": list(PROJECTION_NONCLAIMS),
    }
