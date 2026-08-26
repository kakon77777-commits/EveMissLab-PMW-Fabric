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
from .authority import validate_grant_authority
from .temporal import compare_instants


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
    representation_state_digests: dict[str, str]
    representation_state_heads: dict[str, str]
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
        self.representation_state_digests: dict[str, str] = {}
        self.representation_state_heads: dict[str, str] = {}
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

    def current_state_for(self, event, obj):
        kind = event.event_kind
        if kind.startswith("relation.") and kind != "relation.party_accepted":
            return self.relation_states.get(str(obj["relation_id"]))
        if kind in {"relation.party_accepted", "contract.party_accepted", "contract.party_acceptance_withdrawn"}:
            acceptance = PartyAcceptance.from_dict(obj)
            if acceptance.target_kind == "relation":
                return self.relation_states.get(acceptance.target_id)
            return self.contract_version_states.get(acceptance.target_digest)
        if kind.startswith("contract."):
            contract_id = str(obj["contract_id"])
            digest = str(obj["content_digest"])
            if kind in {
                "contract.drafted",
                "contract.proposed",
                "contract.counterproposed",
                "contract.activated",
                "contract.rejected",
                "contract.withdrawn",
            }:
                prior = self.contract_version_states.get(digest)
                if kind == "contract.activated" and prior == "active":
                    existing = self.active_heads.get(contract_id)
                    if existing is not None and not self.is_ancestor(
                        existing, event.event_id
                    ):
                        return "accepted"
                return prior
            return self.contract_states.get(contract_id)
        if kind.startswith("representation."):
            return self.representation_states.get(
                str(obj["representation_grant_id"])
            )
        if kind.startswith("commitment."):
            return self.commitment_states.get(str(obj["commitment_id"]))
        if kind == "authority_candidate.created":
            return self.contract_states.get(str(obj.get("contract_ref", "")))
        if kind == "authority_candidate.invalidated":
            return self.candidate_states.get(str(obj["content_digest"]))
        if kind == "authority_evaluation.recorded":
            return str(obj.get("candidate_status", "eligible"))
        return None

    def validate_transition(self, event, obj) -> None:
        rule = EVENT_RULES[event.event_kind]
        prior = self.current_state_for(event, obj)
        if prior not in rule.allowed_states:
            if (
                str(obj.get("contract_id", "")) in self.terminal_contracts
                and event.event_kind in FORBIDDEN_AFTER_TERMINAL
            ):
                raise RelationContractError(
                    "terminal_transition_forbidden", str(obj.get("contract_id"))
                )
            raise RelationContractError(
                "lifecycle_transition_invalid",
                f"{event.event_kind}:{prior!r}",
            )

    def evidence_authorities(self) -> dict[str, GrantAuthorityEvidence]:
        result: dict[str, GrantAuthorityEvidence] = {}
        for value in self.objects.values():
            if value.get("schema") == "arcp/grant-authority-evidence/0.1":
                item = GrantAuthorityEvidence.from_dict(value)
                result[item.grant_authority_evidence_id] = item
        return result

    def event_scope(self, event, obj) -> tuple[str, str]:
        if event.event_kind in {
            "contract.party_accepted",
            "contract.party_acceptance_withdrawn",
            "relation.party_accepted",
        }:
            acceptance = PartyAcceptance.from_dict(obj)
            return acceptance.target_kind, acceptance.target_id
        if "contract_id" in obj:
            return "contract", str(obj["contract_id"])
        if "relation_id" in obj:
            return "relation", str(obj["relation_id"])
        if "representation_grant_id" in obj:
            return "representation", str(obj["representation_grant_id"])
        if "contract_ref" in obj:
            return "contract", str(obj["contract_ref"])
        return EVENT_RULES[event.event_kind].object_kind, event.subject_ref

    def validate_event_permissions(
        self,
        event,
        obj,
        authority: GrantAuthorityEvidence | None,
        representation: RepresentationGrant | None,
    ) -> None:
        target_kind, target_ref = self.event_scope(event, obj)
        authority_map = self.evidence_authorities()
        forbidden_refs = {event.object_ref, target_ref}
        forbidden_digests = {event.object_digest}
        if event.representation_grant_ref is not None:
            forbidden_refs.add(event.representation_grant_ref)
        if event.representation_grant_digest is not None:
            forbidden_digests.add(event.representation_grant_digest)

        if authority is not None:
            if (
                event.event_kind not in authority.permitted_lifecycle_actions
                or target_ref not in authority.permitted_contract_scope
            ):
                raise RelationContractError(
                    "transition_authority_scope_mismatch", event.event_id
                )
            validate_grant_authority(
                authority.grant_authority_evidence_id,
                authority_map,
                forbidden_refs,
                forbidden_digests,
            )

        if representation is not None:
            scope = (
                representation.relation_scope
                if target_kind == "relation"
                else representation.contract_scope
            )
            if (
                event.event_kind not in representation.allowed_lifecycle_actions
                or target_ref not in scope
                or event.claimed_actor_ref != representation.representative_ref
            ):
                raise RelationContractError(
                    "representation_scope_mismatch", event.event_id
                )
            if (
                self.representation_states.get(
                    representation.representation_grant_id
                )
                != "active"
                or self.representation_state_digests.get(
                    representation.representation_grant_id
                )
                != representation.content_digest
                or representation.representation_grant_id
                not in self.representation_state_heads
            ):
                raise RelationContractError("representation_inactive", event.event_id)
            if compare_instants(representation.valid_from, event.created_time) not in {
                "before",
                "equal",
            } or compare_instants(event.created_time, representation.expires_at) != "before":
                raise RelationContractError("representation_expired", event.event_id)
            validate_grant_authority(
                representation.grant_authority_ref,
                authority_map,
                forbidden_refs,
                forbidden_digests,
            )
            if event.event_kind in {
                "contract.party_accepted",
                "contract.party_acceptance_withdrawn",
                "relation.party_accepted",
            }:
                acceptance = PartyAcceptance.from_dict(obj)
                if acceptance.party_ref != representation.principal_party_ref:
                    raise RelationContractError(
                        "representation_principal_mismatch", event.event_id
                    )

    def invalidate_contract_candidates(self, contract_id: str) -> None:
        for digest, value in self.candidate_objects.items():
            if value.get("contract_ref") == contract_id:
                self.invalidated_candidate_digests.add(digest)
                self.candidate_states[digest] = "invalidated"

    def invalidate_relation_candidates(self, relation_id: str) -> None:
        for digest, value in self.candidate_objects.items():
            if relation_id in value.get("relation_refs", ()):
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
            self.invalidate_relation_candidates(relation.relation_id)

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
        self.representation_state_digests[
            grant.representation_grant_id
        ] = grant.content_digest
        self.representation_state_heads[grant.representation_grant_id] = event.event_id
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
            dict(sorted(self.representation_state_digests.items())),
            dict(sorted(self.representation_state_heads.items())),
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
        state.validate_transition(event, obj)
        authority_value = _verify_evidence_pair(
            event,
            objects_by_digest,
            ref=event.lifecycle_transition_authority_ref,
            digest=event.lifecycle_transition_authority_digest,
            kind="transition_authority",
        )
        authority = (
            None
            if authority_value is None
            else GrantAuthorityEvidence.from_dict(authority_value)
        )
        representation_value = _verify_evidence_pair(
            event,
            objects_by_digest,
            ref=event.representation_grant_ref,
            digest=event.representation_grant_digest,
            kind="representation_grant",
        )
        representation = (
            None
            if representation_value is None
            else RepresentationGrant.from_dict(representation_value)
        )
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
        state.validate_event_permissions(
            event, obj, authority, representation
        )
        EVENT_RULES[event.event_kind].effect_handler(state, event, obj)
    return state.projection()
