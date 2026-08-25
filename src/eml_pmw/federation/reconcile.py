from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any

from eml_wake.canonical import canonical_bytes, loads_strict

from .authority import AuthorityVerifier, verify_event_authority
from .causal import classify_relation, validate_graph
from .errors import FederationError
from .models import FederatedEvent
from .store import FederationStore


CONFLICT_PRIORITY = {
    "content_collision": 0,
    "causal_history_conflict": 1,
    "authority_conflict": 2,
    "identity_reference_conflict": 3,
    "state_transition_conflict": 4,
    "field_value_conflict": 5,
    "concurrent_nonexclusive": 6,
}


@dataclass(frozen=True)
class ConflictAnalysis:
    status: str
    conflict_class: str
    member_event_ids: tuple[str, ...]
    subject_ref: str


@dataclass(frozen=True)
class ReconciliationDecision:
    status: str
    event_id: str
    conflict_id: str | None = None
    conflict_class: str | None = None
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolutionResult:
    status: str
    conflict_id: str
    resolution_event_id: str
    resolution_path: str


def _payload_object(data: bytes, event_id: str) -> dict[str, Any]:
    try:
        value = loads_strict(data)
    except Exception as error:
        raise FederationError("conflict_payload_invalid", event_id) from error
    if not isinstance(value, dict):
        raise FederationError("conflict_payload_invalid", event_id)
    return value


def detect_conflict(
    left: FederatedEvent,
    left_payload: bytes,
    right: FederatedEvent,
    right_payload: bytes,
    *,
    known_events: tuple[FederatedEvent, ...] | None = None,
) -> ConflictAnalysis:
    members = tuple(sorted((left.event_id, right.event_id)))
    subject = left.subject_ref if left.subject_ref == right.subject_ref else "multiple"
    if left.event_id == right.event_id and left.core_digest != right.core_digest:
        return ConflictAnalysis("conflict", "content_collision", members, subject)
    if known_events is None:
        known_ids = {left.event_id, right.event_id}
        if any(
            parent not in known_ids
            for event in (left, right)
            for parent in event.causal_parents
        ):
            return ConflictAnalysis(
                "conflict", "causal_history_conflict", members, subject
            )
        ordered = (
            left.event_id in right.causal_parents
            or right.event_id in left.causal_parents
        )
    else:
        graph = validate_graph(known_events)
        if not graph.valid:
            return ConflictAnalysis(
                "conflict", "causal_history_conflict", members, subject
            )
        ordered = classify_relation(
            known_events, left.event_id, right.event_id
        ) in {"before", "after", "same"}
    if ordered:
        return ConflictAnalysis(
            "ordered", "concurrent_nonexclusive", members, subject
        )
    if left.subject_ref != right.subject_ref:
        return ConflictAnalysis(
            "parallel_branch", "concurrent_nonexclusive", members, "multiple"
        )
    if left.authority_ref != right.authority_ref:
        return ConflictAnalysis("conflict", "authority_conflict", members, subject)

    left_value = _payload_object(left_payload, left.event_id)
    right_value = _payload_object(right_payload, right.event_id)
    if left.event_kind.startswith("ral.identity.") or right.event_kind.startswith(
        "ral.identity."
    ):
        return ConflictAnalysis(
            "conflict", "identity_reference_conflict", members, subject
        )
    if left.event_kind.endswith("state_transition") or right.event_kind.endswith(
        "state_transition"
    ):
        return ConflictAnalysis(
            "conflict", "state_transition_conflict", members, subject
        )
    if (
        left_value.get("field") == right_value.get("field")
        and left_value.get("value") != right_value.get("value")
    ):
        return ConflictAnalysis("conflict", "field_value_conflict", members, subject)
    return ConflictAnalysis(
        "parallel_branch", "concurrent_nonexclusive", members, subject
    )


def _conflict_record(
    analysis: ConflictAnalysis,
    left: FederatedEvent,
    right: FederatedEvent,
) -> dict[str, Any]:
    digests = {
        left.event_id: left.core_digest,
        right.event_id: right.core_digest,
    }
    core = {
        "conflict_class": analysis.conflict_class,
        "subject_ref": analysis.subject_ref,
        "member_event_ids": list(analysis.member_event_ids),
        "member_event_digests": [digests[event_id] for event_id in analysis.member_event_ids],
    }
    conflict_id = "conflict:sha256:" + hashlib.sha256(canonical_bytes(core)).hexdigest()
    return {
        "schema": "pmw-federation-conflict/v1",
        "conflict_id": conflict_id,
        **core,
        "not_claimed": [
            "conflict_resolved",
            "authority_to_execute",
            "resident_identity_continuity",
        ],
    }


def reconcile_event(
    store: FederationStore,
    event_id: str,
    *,
    verifier: AuthorityVerifier | None = None,
) -> ReconciliationDecision:
    event = store.get_event(event_id)
    authority = verify_event_authority(
        event, store.config, verifier, action="adopt_event"
    )
    if authority.status == "unmeasured":
        return ReconciliationDecision(
            "unmeasured", event_id, reason_codes=("authority_unmeasured",)
        )
    if authority.status == "rejected":
        return ReconciliationDecision(
            "rejected", event_id, reason_codes=("authority_rejected",)
        )

    candidates: list[tuple[ConflictAnalysis, FederatedEvent]] = []
    payload = store.event_payload(event)
    all_events = store.events()
    for other in all_events:
        if other.event_id == event_id:
            continue
        analysis = detect_conflict(
            other,
            store.event_payload(other),
            event,
            payload,
            known_events=all_events,
        )
        if analysis.conflict_class != "concurrent_nonexclusive":
            candidates.append((analysis, other))
    if not candidates:
        return ReconciliationDecision("adopted", event_id)

    analysis, other = min(
        candidates, key=lambda item: CONFLICT_PRIORITY[item[0].conflict_class]
    )
    record = _conflict_record(analysis, other, event)
    conflict_id = record["conflict_id"]
    store.record_conflict(conflict_id, record)
    return ReconciliationDecision(
        "conflict",
        event_id,
        conflict_id=conflict_id,
        conflict_class=analysis.conflict_class,
    )


def resolve_conflict(
    store: FederationStore,
    conflict_id: str,
    resolution_event: FederatedEvent,
    payload: bytes,
    *,
    verifier: AuthorityVerifier | None,
) -> ResolutionResult:
    conflict = store.get_conflict(conflict_id)
    if (
        resolution_event.event_kind != "pmw.conflict.resolution"
        or resolution_event.subject_ref != conflict_id
    ):
        raise FederationError("resolution_subject_mismatch", conflict_id)
    authority = verify_event_authority(
        resolution_event,
        store.config,
        verifier,
        action="resolve_conflict",
        subject_ref=conflict_id,
    )
    if authority.status != "verified":
        raise FederationError("resolution_authority_unverified", conflict_id)

    value = _payload_object(payload, resolution_event.event_id)
    if set(value) != {"conflict_id", "member_event_ids", "selected_event_id"}:
        raise FederationError("resolution_payload_invalid", conflict_id)
    members = tuple(conflict["member_event_ids"])
    if value["conflict_id"] != conflict_id:
        raise FederationError("resolution_subject_mismatch", conflict_id)
    if tuple(sorted(value["member_event_ids"])) != tuple(sorted(members)):
        raise FederationError("conflict_members_incomplete", conflict_id)
    if value["selected_event_id"] not in members:
        raise FederationError("resolution_selection_invalid", conflict_id)
    if set(resolution_event.causal_parents) != set(members):
        raise FederationError("resolution_parents_incomplete", conflict_id)

    store.submit(
        resolution_event,
        payload,
        delivery_id=f"resolution:{resolution_event.event_id}",
    )
    record = {
        "schema": "pmw-federation-resolution/v1",
        "conflict_id": conflict_id,
        "resolution_event_id": resolution_event.event_id,
        "resolution_event_digest": resolution_event.core_digest,
        "authority_ref": resolution_event.authority_ref,
        "authority_evidence_ref": authority.evidence_ref,
        "member_event_ids": list(sorted(members)),
        "selected_event_id": value["selected_event_id"],
        "not_claimed": [
            "source_events_rewritten",
            "ral_head_mutated",
            "resident_identity_continuity",
        ],
    }
    path = store.record_resolution(conflict_id, resolution_event.event_id, record)
    return ResolutionResult("resolved", conflict_id, resolution_event.event_id, str(path))
