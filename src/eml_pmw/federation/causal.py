from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .errors import FederationError
from .models import FederatedEvent


@dataclass(frozen=True)
class CausalValidation:
    valid: bool
    code: str | None
    missing_parent_ids: tuple[str, ...] = ()
    cycle_event_ids: tuple[str, ...] = ()


def _event_map(events: Iterable[FederatedEvent]) -> dict[str, FederatedEvent]:
    by_id: dict[str, FederatedEvent] = {}
    for event in events:
        existing = by_id.get(event.event_id)
        if existing is not None and existing.core_digest != event.core_digest:
            raise FederationError("event_content_collision", event.event_id)
        by_id[event.event_id] = event
    return by_id


def _cycle(by_id: dict[str, FederatedEvent]) -> tuple[str, ...]:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(event_id: str) -> tuple[str, ...]:
        if event_id in visited:
            return ()
        if event_id in visiting:
            start = stack.index(event_id)
            return tuple(stack[start:] + [event_id])
        visiting.add(event_id)
        stack.append(event_id)
        for parent_id in by_id[event_id].causal_parents:
            if parent_id in by_id:
                found = visit(parent_id)
                if found:
                    return found
        stack.pop()
        visiting.remove(event_id)
        visited.add(event_id)
        return ()

    for event_id in sorted(by_id):
        found = visit(event_id)
        if found:
            return found
    return ()


def validate_graph(events: Iterable[FederatedEvent]) -> CausalValidation:
    items = tuple(events)
    try:
        by_id = _event_map(items)
    except FederationError as error:
        return CausalValidation(False, error.code)

    sequence_owner: dict[tuple[str, str, int], str] = {}
    for event in items:
        key = (
            event.replica_ref.replica_id,
            event.replica_ref.store_generation,
            event.replica_seq,
        )
        owner = sequence_owner.get(key)
        if owner is not None and owner != event.event_id:
            return CausalValidation(False, "replica_sequence_collision")
        sequence_owner[key] = event.event_id

    cycle = _cycle(by_id)
    if cycle:
        return CausalValidation(False, "causal_cycle", cycle_event_ids=cycle)

    missing = sorted(
        {
            parent_id
            for event in items
            for parent_id in event.causal_parents
            if parent_id not in by_id
        }
    )
    if missing:
        return CausalValidation(
            False, "pending_dependencies", missing_parent_ids=tuple(missing)
        )
    return CausalValidation(True, None)


def derive_heads(events: Iterable[FederatedEvent]) -> tuple[str, ...]:
    items = tuple(events)
    result = validate_graph(items)
    if not result.valid:
        raise FederationError(result.code or "causal_graph_invalid", "cannot derive heads")
    parent_ids = {parent for event in items for parent in event.causal_parents}
    return tuple(sorted(event.event_id for event in items if event.event_id not in parent_ids))


def _is_ancestor(
    by_id: dict[str, FederatedEvent], ancestor_id: str, descendant_id: str
) -> bool:
    pending = list(by_id[descendant_id].causal_parents)
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == ancestor_id:
            return True
        if current in visited or current not in by_id:
            continue
        visited.add(current)
        pending.extend(by_id[current].causal_parents)
    return False


def classify_relation(
    events: Iterable[FederatedEvent], left_id: str, right_id: str
) -> str:
    items = tuple(events)
    result = validate_graph(items)
    if not result.valid:
        raise FederationError(result.code or "causal_graph_invalid", "cannot classify")
    by_id = _event_map(items)
    if left_id not in by_id or right_id not in by_id:
        raise FederationError("event_not_found", f"{left_id} / {right_id}")
    if left_id == right_id:
        return "same"
    if _is_ancestor(by_id, left_id, right_id):
        return "before"
    if _is_ancestor(by_id, right_id, left_id):
        return "after"
    return "concurrent"
