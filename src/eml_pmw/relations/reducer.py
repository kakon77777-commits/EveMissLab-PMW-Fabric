from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .canonical import object_content_digest
from .errors import RelationContractError
from .events import EVENT_RULES, RelationContractEvent
from .models_authority import (
    GrantAuthorityEvidence,
    PartyAcceptance,
    RepresentationGrant,
)
from .models_relation import RelationVersion


TERMINAL_CONTRACT_EVENTS = {"contract.terminated", "contract.expired"}
FORBIDDEN_AFTER_TERMINAL = {
    "contract.party_accepted",
    "contract.party_acceptance_withdrawn",
    "contract.activated",
    "contract.amendment_proposed",
    "contract.resumed",
}


def _object_ref(value: Mapping[str, Any]) -> str:
    for field in (
        "relation_id",
        "contract_id",
        "acceptance_id",
        "representation_grant_id",
        "commitment_id",
        "candidate_id",
        "receipt_id",
        "grant_authority_evidence_id",
    ):
        if field in value:
            return str(value[field])
    raise RelationContractError("object_ref_invalid", str(value.get("schema")))


@dataclass(frozen=True)
class LifecycleProjection:
    relation_states: dict[str, str]
    contract_states: dict[str, str]
    contract_version_states: dict[str, str]
    active_heads: dict[str, str]
    active_head_digests: dict[str, str]
    acceptances: dict[str, tuple[str, ...]]
    representation_states: dict[str, str]
    commitment_states: dict[str, str]
    candidate_states: dict[str, str]
    evaluation_states: dict[str, str]
    conflicts: tuple[str, ...]
    invalidated_candidate_digests: tuple[str, ...]


class _ReducerState:
    def __init__(self, objects: Mapping[str, dict[str, Any]], parents):
        self.objects = objects
        self.parents = parents
        self.relation_states: dict[str, str] = {}
        self.contract_states: dict[str, str] = {}
        self.contract_version_states: dict[str, str] = {}
        self.active_heads: dict[str, str] = {}
        self.active_head_digests: dict[str, str] = {}
        self.acceptances_by_target: dict[str, dict[str, PartyAcceptance]] = {}
        self.representation_states: dict[str, str] = {}
        self.commitment_states: dict[str, str] = {}
        self.candidate_states: dict[str, str] = {}
        self.candidate_objects: dict[str, dict[str, Any]] = {}
        self.evaluation_states: dict[str, str] = {}
        self.conflicts: set[str] = set()
        self.invalidated_candidate_digests: set[str] = set()
        self.terminal_contracts: set[str] = set()

    def is_ancestor(self, ancestor: str, descendant: str) -> bool:
        pending = list(self.parents.get(descendant, ()))
        seen: set[str] = set()
        while pending:
            item = pending.pop()
            if item == ancestor:
                return True
            if item in seen:
                continue
            seen.add(item)
            pending.extend(self.parents.get(item, ()))
        return False

    def invalidate_contract_candidates(self, contract_id: str) -> None:
        for digest, value in self.candidate_objects.items():
            if value.get("contract_ref") == contract_id:
                self.invalidated_candidate_digests.add(digest)
                self.candidate_states[digest] = "invalidated"

    def apply_relation(self, event, obj):
        relation = RelationVersion.from_dict(obj)
        states = {
            "relation.recorded": "observed",
            "relation.proposed": "proposed",
            "relation.disputed": "disputed",
            "relation.withdrawn": "withdrawn",
            "relation.superseded": "superseded",
        }
        self.relation_states[relation.relation_id] = states[event.event_kind]
        if states[event.event_kind] in {"withdrawn", "superseded"}:
            self.invalidate_contract_candidates(relation.relation_id)

    def apply_acceptance(self, event, obj):
        acceptance = PartyAcceptance.from_dict(obj)
        target = self.objects.get(acceptance.target_digest)
        if target is None:
            raise RelationContractError("acceptance_target_missing", acceptance.target_id)
        if acceptance.target_id != _object_ref(target):
            raise RelationContractError("acceptance_target_kind_mismatch", acceptance.target_id)
        accepted = self.acceptances_by_target.setdefault(acceptance.target_digest, {})
        if event.event_kind == "contract.party_acceptance_withdrawn":
            accepted.pop(acceptance.party_ref, None)
            if acceptance.target_id in self.active_heads:
                self.contract_states[acceptance.target_id] = "suspended"
                self.invalidate_contract_candidates(acceptance.target_id)
            else:
                self.contract_version_states[acceptance.target_digest] = "proposed"
            return
        accepted[acceptance.party_ref] = acceptance
        if acceptance.target_kind == "contract":
            required = {
                item["party_ref"]
                for item in target["party_terms"]
                if item["acceptance_required"]
            }
            self.contract_version_states[acceptance.target_digest] = (
                "accepted" if required <= set(accepted) else "partially_accepted"
            )
            self.contract_states[acceptance.target_id] = self.contract_version_states[
                acceptance.target_digest
            ]
        else:
            required = set(target["party_refs"])
            self.relation_states[acceptance.target_id] = (
                "accepted" if required <= set(accepted) else "partially_accepted"
            )

    def apply_contract(self, event, obj):
        contract_id = str(obj["contract_id"])
        digest = str(obj["content_digest"])
        if contract_id in self.terminal_contracts and event.event_kind in FORBIDDEN_AFTER_TERMINAL:
            raise RelationContractError("terminal_transition_forbidden", contract_id)
        if event.event_kind == "contract.drafted":
            self.contract_version_states[digest] = "draft"
            self.contract_states[contract_id] = "draft"
        elif event.event_kind == "contract.proposed":
            self.contract_version_states[digest] = "proposed"
            self.contract_states[contract_id] = "proposed"
        elif event.event_kind == "contract.counterproposed":
            self.contract_version_states[digest] = "negotiating"
            self.contract_states[contract_id] = "negotiating"
        elif event.event_kind == "contract.amendment_proposed":
            self.contract_version_states[digest] = "proposed"
        elif event.event_kind == "contract.activated":
            if self.contract_version_states.get(digest) not in {"accepted", "active"}:
                raise RelationContractError("contract_not_accepted", contract_id)
            current = self.active_heads.get(contract_id)
            if current is None:
                if event.supersedes_active_head is not None:
                    raise RelationContractError("active_head_mismatch", contract_id)
                self.active_heads[contract_id] = event.event_id
                self.active_head_digests[contract_id] = digest
                self.contract_states[contract_id] = "active"
            elif event.supersedes_active_head == current:
                old_digest = self.active_head_digests[contract_id]
                self.active_heads[contract_id] = event.event_id
                self.active_head_digests[contract_id] = digest
                self.contract_version_states[old_digest] = "inactive"
                self.contract_states[contract_id] = "active"
                self.invalidate_contract_candidates(contract_id)
            elif not self.is_ancestor(current, event.event_id):
                self.conflicts.add(contract_id)
                self.active_heads.pop(contract_id, None)
                self.active_head_digests.pop(contract_id, None)
                self.contract_states[contract_id] = "conflicted_heads"
            else:
                raise RelationContractError("active_head_mismatch", contract_id)
            self.contract_version_states[digest] = "active"
        elif event.event_kind == "contract.suspended":
            self.contract_states[contract_id] = "suspended"
            self.invalidate_contract_candidates(contract_id)
        elif event.event_kind == "contract.resumed":
            self.contract_states[contract_id] = "active"
        elif event.event_kind in TERMINAL_CONTRACT_EVENTS:
            state = event.event_kind.split(".", 1)[1]
            self.contract_states[contract_id] = state
            self.contract_version_states[digest] = state
            self.terminal_contracts.add(contract_id)
            self.active_heads.pop(contract_id, None)
            self.active_head_digests.pop(contract_id, None)
            self.invalidate_contract_candidates(contract_id)
        elif event.event_kind in {"contract.rejected", "contract.withdrawn"}:
            state = event.event_kind.split(".", 1)[1]
            self.contract_states[contract_id] = state
            self.contract_version_states[digest] = state
            self.invalidate_contract_candidates(contract_id)
        elif event.event_kind == "contract.corrected":
            self.contract_version_states[digest] = "corrected"
            self.invalidate_contract_candidates(contract_id)
        elif event.event_kind == "contract.tombstoned":
            self.contract_version_states[digest] = "tombstoned"
            self.contract_states[contract_id] = "tombstoned"
            self.terminal_contracts.add(contract_id)
            self.invalidate_contract_candidates(contract_id)

    def apply_representation(self, event, obj):
        grant = RepresentationGrant.from_dict(obj)
        state = {
            "representation.granted": "active",
            "representation.suspended": "suspended",
            "representation.revoked": "revoked",
            "representation.expired": "expired",
        }[event.event_kind]
        self.representation_states[grant.representation_grant_id] = state
        if state != "active":
            for digest in tuple(self.candidate_states):
                self.invalidated_candidate_digests.add(digest)
                self.candidate_states[digest] = "invalidated"

    def apply_commitment(self, event, obj):
        self.commitment_states[str(obj["commitment_id"])] = str(obj["status"])

    def apply_candidate(self, event, obj):
        digest = str(obj["content_digest"])
        self.candidate_objects[digest] = obj
        if event.event_kind == "authority_candidate.invalidated":
            self.candidate_states[digest] = "invalidated"
            self.invalidated_candidate_digests.add(digest)
        else:
            self.candidate_states[digest] = "recorded"

    def apply_evaluation(self, event, obj):
        self.evaluation_states[event.object_ref] = "recorded"

    def projection(self) -> LifecycleProjection:
        return LifecycleProjection(
            dict(sorted(self.relation_states.items())),
            dict(sorted(self.contract_states.items())),
            dict(sorted(self.contract_version_states.items())),
            dict(sorted(self.active_heads.items())),
            dict(sorted(self.active_head_digests.items())),
            {
                digest: tuple(sorted(items))
                for digest, items in sorted(self.acceptances_by_target.items())
            },
            dict(sorted(self.representation_states.items())),
            dict(sorted(self.commitment_states.items())),
            dict(sorted(self.candidate_states.items())),
            dict(sorted(self.evaluation_states.items())),
            tuple(sorted(self.conflicts)),
            tuple(sorted(self.invalidated_candidate_digests)),
        )


def _topological(events: tuple[RelationContractEvent, ...]):
    by_id: dict[str, RelationContractEvent] = {}
    for event in events:
        existing = by_id.get(event.event_id)
        if existing is not None:
            if existing.event_digest != event.event_digest:
                raise RelationContractError("event_id_collision", event.event_id)
            continue
        by_id[event.event_id] = event
    for event in by_id.values():
        missing = sorted(set(event.causal_parents) - set(by_id))
        if missing:
            raise RelationContractError("contract_parent_missing", missing[0])
    remaining = set(by_id)
    emitted: set[str] = set()
    result: list[RelationContractEvent] = []
    while remaining:
        ready = [
            by_id[item]
            for item in remaining
            if set(by_id[item].causal_parents) <= emitted
        ]
        if not ready:
            raise RelationContractError("causal_cycle", "event graph")
        for event in sorted(ready, key=lambda item: item.event_digest):
            result.append(event)
            emitted.add(event.event_id)
            remaining.remove(event.event_id)
    return tuple(result), by_id


def _verified_object(
    event: RelationContractEvent, objects: Mapping[str, dict[str, Any]]
) -> dict[str, Any]:
    obj = objects.get(event.object_digest)
    if (
        obj is None
        or obj.get("content_digest") != event.object_digest
        or object_content_digest(obj) != event.object_digest
    ):
        raise RelationContractError("object_digest_mismatch", event.event_id)
    if _object_ref(obj) != event.object_ref:
        raise RelationContractError("object_ref_invalid", event.event_id)
    return obj


def _verify_evidence_pair(
    event: RelationContractEvent,
    objects: Mapping[str, dict[str, Any]],
    *,
    ref: str | None,
    digest: str | None,
    kind: str,
) -> dict[str, Any] | None:
    if ref is None and digest is None:
        return None
    obj = objects.get(str(digest))
    if (
        obj is None
        or obj.get("content_digest") != digest
        or object_content_digest(obj) != digest
        or _object_ref(obj) != ref
    ):
        raise RelationContractError(f"{kind}_digest_mismatch", event.event_id)
    return obj


def reduce_events(
    events: Iterable[RelationContractEvent],
    objects_by_digest: Mapping[str, dict[str, Any]],
) -> LifecycleProjection:
    ordered, by_id = _topological(tuple(events))
    state = _ReducerState(
        objects_by_digest,
        {event_id: event.causal_parents for event_id, event in by_id.items()},
    )
    for event in ordered:
        obj = _verified_object(event, objects_by_digest)
        authority = _verify_evidence_pair(
            event,
            objects_by_digest,
            ref=event.lifecycle_transition_authority_ref,
            digest=event.lifecycle_transition_authority_digest,
            kind="transition_authority",
        )
        if authority is not None:
            GrantAuthorityEvidence.from_dict(authority)
        representation = _verify_evidence_pair(
            event,
            objects_by_digest,
            ref=event.representation_grant_ref,
            digest=event.representation_grant_digest,
            kind="representation_grant",
        )
        if representation is not None:
            RepresentationGrant.from_dict(representation)
        if event.event_kind in {
            "contract.party_accepted",
            "contract.party_acceptance_withdrawn",
            "relation.party_accepted",
        }:
            acceptance = PartyAcceptance.from_dict(obj)
            if (
                acceptance.representation_grant_ref
                != event.representation_grant_ref
                or acceptance.representation_grant_digest
                != event.representation_grant_digest
            ):
                raise RelationContractError(
                    "representation_grant_digest_mismatch", event.event_id
                )
        EVENT_RULES[event.event_kind].effect_handler(state, event, obj)
    return state.projection()
