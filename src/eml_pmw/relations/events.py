from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any, Callable

from eml_wake.canonical import canonical_bytes

from .errors import RelationContractError
from .models_common import (
    require_exact,
    unique_refs,
    unique_strings,
    validate_digest_ref,
)
from .references import validate_portable_ref
from .temporal import NormalizedInstantEvidence


EVENT_CANON = "arcp-relation-contract-event-json-nfc-codepoint-v1"
EVENT_DOMAIN = b"ARCP-RELATION-CONTRACT-EVENT\x00"
EVENT_FIELDS = {
    "schema",
    "event_id",
    "event_kind",
    "subject_ref",
    "object_ref",
    "object_digest",
    "causal_parents",
    "claimed_actor_ref",
    "representation_grant_ref",
    "representation_grant_digest",
    "lifecycle_transition_authority_ref",
    "lifecycle_transition_authority_digest",
    "supersedes_active_head",
    "acceptance_set_digest",
    "representation_set_digest",
    "party_evidence_set_digest",
    "activation_policy_digest",
    "created_time",
    "local_recorded_at",
    "correction_of",
    "withdraws",
    "not_claimed",
}
REQUIRED_EVENT_NONCLAIMS = (
    "capability_granted",
    "economic_compensation",
    "global_causal_order",
    "provider_execution",
    "resident_identity_continuity",
)


def _relation_effect(state, event, obj):
    state.apply_relation(event, obj)


def _contract_effect(state, event, obj):
    state.apply_contract(event, obj)


def _acceptance_effect(state, event, obj):
    state.apply_acceptance(event, obj)


def _representation_effect(state, event, obj):
    state.apply_representation(event, obj)


def _commitment_effect(state, event, obj):
    state.apply_commitment(event, obj)


def _candidate_effect(state, event, obj):
    state.apply_candidate(event, obj)


def _evaluation_effect(state, event, obj):
    state.apply_evaluation(event, obj)


@dataclass(frozen=True)
class TransitionRule:
    object_kind: str
    allowed_states: tuple[str | None, ...]
    terminal: bool
    authority_mode: str
    required_evidence: tuple[str, ...]
    effect_handler: Callable[[Any, Any, dict[str, Any]], None]


def _rule(kind, states, terminal, authority, evidence, handler):
    return TransitionRule(kind, tuple(states), terminal, authority, tuple(evidence), handler)


EVENT_RULES = {
    "relation.recorded": _rule("relation", (None,), False, "none", ("source",), _relation_effect),
    "relation.proposed": _rule("relation", (None, "disputed"), False, "required", ("representation", "party_pin"), _relation_effect),
    "relation.party_accepted": _rule("acceptance", ("proposed", "partially_accepted"), False, "representation", ("acceptance", "party_pin"), _acceptance_effect),
    "relation.disputed": _rule("relation", ("observed", "proposed", "accepted"), False, "party_evidence", ("party_pin",), _relation_effect),
    "relation.withdrawn": _rule("relation", ("observed", "proposed", "disputed"), True, "required", ("representation",), _relation_effect),
    "relation.superseded": _rule("relation", ("observed", "accepted", "disputed"), True, "required", ("replacement",), _relation_effect),
    "contract.drafted": _rule("contract", (None,), False, "none", (), _contract_effect),
    "contract.proposed": _rule("contract", ("draft", "negotiating"), False, "required", ("representation",), _contract_effect),
    "contract.counterproposed": _rule("contract", ("proposed", "negotiating"), False, "representation", ("new_digest",), _contract_effect),
    "contract.party_accepted": _rule("acceptance", ("proposed", "negotiating", "partially_accepted"), False, "representation", ("acceptance", "party_pin"), _acceptance_effect),
    "contract.party_acceptance_withdrawn": _rule("acceptance", ("proposed", "negotiating", "accepted", "active"), False, "representation", ("acceptance",), _acceptance_effect),
    "contract.rejected": _rule("contract", ("proposed", "negotiating", "accepted"), True, "representation", ("party_evidence",), _contract_effect),
    "contract.withdrawn": _rule("contract", ("draft", "proposed", "negotiating", "accepted"), True, "required", ("representation",), _contract_effect),
    "contract.activated": _rule("contract", ("accepted",), False, "required", ("activation_sets", "representation"), _contract_effect),
    "contract.amendment_proposed": _rule("contract", ("active", "suspended"), False, "required", ("new_version", "representation"), _contract_effect),
    "contract.suspended": _rule("contract", ("active",), False, "required", (), _contract_effect),
    "contract.resumed": _rule("contract", ("suspended",), False, "required", ("fresh_sets", "representation"), _contract_effect),
    "contract.terminated": _rule("contract", ("active", "suspended"), True, "required", ("exit_path", "representation"), _contract_effect),
    "contract.expired": _rule("contract", ("draft", "proposed", "negotiating", "accepted", "active", "suspended"), True, "clock", ("normalized_time",), _contract_effect),
    "contract.corrected": _rule("contract", ("draft", "proposed", "negotiating", "accepted", "active", "suspended", "terminated", "expired"), True, "required", ("replacement",), _contract_effect),
    "contract.tombstoned": _rule("contract", ("draft", "proposed", "negotiating", "accepted", "active", "suspended", "terminated", "expired", "corrected"), True, "required", ("tombstone",), _contract_effect),
    "representation.granted": _rule("representation", (None,), False, "required", ("grant_authority", "party_pin"), _representation_effect),
    "representation.suspended": _rule("representation", ("active",), False, "required", (), _representation_effect),
    "representation.revoked": _rule("representation", ("active", "suspended"), True, "required", (), _representation_effect),
    "representation.expired": _rule("representation", ("active", "suspended"), True, "clock", ("normalized_time",), _representation_effect),
    "commitment.created": _rule("commitment", (None,), False, "contract", ("active_contract",), _commitment_effect),
    "commitment.status_changed": _rule("commitment", ("planned", "active", "satisfied", "breached", "waived"), False, "contract", ("parent_version",), _commitment_effect),
    "authority_candidate.created": _rule("candidate", ("active",), False, "derived", ("fresh_sets",), _candidate_effect),
    "authority_candidate.invalidated": _rule("candidate", ("recorded", "current"), True, "derived", ("causal_invalidator",), _candidate_effect),
    "authority_evaluation.recorded": _rule("evaluation", ("eligible",), False, "evaluator", ("candidate_digest",), _evaluation_effect),
}
EVENT_KINDS = frozenset(EVENT_RULES)
AUTHORITY_REQUIRED_KINDS = frozenset(
    kind for kind, rule in EVENT_RULES.items() if rule.authority_mode == "required"
)
REPRESENTATION_REQUIRED_KINDS = frozenset(
    kind
    for kind, rule in EVENT_RULES.items()
    if "representation" in rule.required_evidence
    or rule.authority_mode == "representation"
)


@dataclass(frozen=True)
class RelationContractEvent:
    schema: str
    event_id: str
    event_kind: str
    subject_ref: str
    object_ref: str
    object_digest: str
    causal_parents: tuple[str, ...]
    claimed_actor_ref: str | None
    representation_grant_ref: str | None
    representation_grant_digest: str | None
    lifecycle_transition_authority_ref: str | None
    lifecycle_transition_authority_digest: str | None
    supersedes_active_head: str | None
    acceptance_set_digest: str | None
    representation_set_digest: str | None
    party_evidence_set_digest: str | None
    activation_policy_digest: str | None
    created_time: NormalizedInstantEvidence
    local_recorded_at: str
    correction_of: str | None
    withdraws: str | None
    not_claimed: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "RelationContractEvent":
        require_exact(value, EVENT_FIELDS, "relation contract event")
        kind = value["event_kind"]
        if kind not in EVENT_KINDS:
            raise RelationContractError("event_kind_not_allowed", str(kind))
        event_id = validate_portable_ref(value["event_id"], "event_id")
        parents = unique_refs(value["causal_parents"], "causal_parents", allow_empty=True)
        if event_id in parents:
            raise RelationContractError("causal_parents_invalid", event_id)
        authority_ref = value["lifecycle_transition_authority_ref"]
        authority_digest = value["lifecycle_transition_authority_digest"]
        if (authority_ref is None) != (authority_digest is None):
            raise RelationContractError("transition_authority_digest_mismatch", event_id)
        if kind in AUTHORITY_REQUIRED_KINDS and authority_ref is None:
            raise RelationContractError("transition_authority_missing", event_id)
        if authority_ref is not None:
            authority_ref = validate_portable_ref(
                authority_ref, "lifecycle_transition_authority_ref"
            )
            authority_digest = validate_digest_ref(
                authority_digest, "lifecycle_transition_authority_digest"
            )
        representation_ref = value["representation_grant_ref"]
        representation_digest = value["representation_grant_digest"]
        if (representation_ref is None) != (representation_digest is None):
            raise RelationContractError("representation_grant_digest_mismatch", event_id)
        if kind in REPRESENTATION_REQUIRED_KINDS and representation_ref is None:
            raise RelationContractError("representation_missing", event_id)
        if representation_ref is not None:
            representation_ref = validate_portable_ref(
                representation_ref, "representation_grant_ref"
            )
            representation_digest = validate_digest_ref(
                representation_digest, "representation_grant_digest"
            )
        activation_fields = (
            "acceptance_set_digest",
            "representation_set_digest",
            "party_evidence_set_digest",
            "activation_policy_digest",
        )
        if kind == "contract.activated":
            if any(value[field] is None for field in activation_fields):
                raise RelationContractError("activation_evidence_missing", event_id)
            for field in activation_fields:
                validate_digest_ref(value[field], field)
        elif any(value[field] is not None for field in activation_fields):
            raise RelationContractError("activation_evidence_unexpected", event_id)
        if (
            not isinstance(value["local_recorded_at"], str)
            or not value["local_recorded_at"]
        ):
            raise RelationContractError("event_field_invalid", "local_recorded_at")
        not_claimed = unique_strings(value["not_claimed"], "not_claimed")
        if set(not_claimed) != set(REQUIRED_EVENT_NONCLAIMS):
            raise RelationContractError("not_claimed_incomplete", event_id)
        optional_refs = {}
        for field in ("claimed_actor_ref", "supersedes_active_head", "correction_of", "withdraws"):
            item = value[field]
            optional_refs[field] = (
                None if item is None else validate_portable_ref(item, field)
            )
        return cls(
            value["schema"],
            event_id,
            kind,
            validate_portable_ref(value["subject_ref"], "subject_ref"),
            validate_portable_ref(value["object_ref"], "object_ref"),
            validate_digest_ref(value["object_digest"], "object_digest"),
            parents,
            optional_refs["claimed_actor_ref"],
            representation_ref,
            representation_digest,
            authority_ref,
            authority_digest,
            optional_refs["supersedes_active_head"],
            value["acceptance_set_digest"],
            value["representation_set_digest"],
            value["party_evidence_set_digest"],
            value["activation_policy_digest"],
            NormalizedInstantEvidence.from_dict(value["created_time"]),
            value["local_recorded_at"],
            optional_refs["correction_of"],
            optional_refs["withdraws"],
            tuple(sorted(not_claimed)),
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["causal_parents"] = list(self.causal_parents)
        value["created_time"] = self.created_time.to_dict()
        value["not_claimed"] = list(self.not_claimed)
        return value

    @property
    def event_digest(self) -> str:
        body = EVENT_DOMAIN + EVENT_CANON.encode("ascii") + b"\x00" + canonical_bytes(
            self.to_dict()
        )
        return f"sha256:{EVENT_CANON}:" + hashlib.sha256(body).hexdigest()
