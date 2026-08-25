from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any

from eml_wake.canonical import canonical_bytes, loads_strict

from .errors import FederationError
from .models import FederatedEvent
from .store import FederationStore


PROJECTION_SCHEMA = "pmw-federation-projection/v1"
PROJECTION_NONCLAIMS = [
    "global_causal_order",
    "source_history_rewritten",
    "ral_head_mutated",
    "resident_identity_continuity",
]


@dataclass(frozen=True)
class ProjectionDifference:
    path: str
    kind: str


@dataclass(frozen=True)
class ProjectionComparison:
    status: str
    differences: tuple[ProjectionDifference, ...]


def _payload_value(store: FederationStore, event: FederatedEvent) -> dict[str, Any] | None:
    try:
        value = loads_strict(store.event_payload(event))
    except Exception as error:
        raise FederationError("projection_payload_invalid", event.event_id) from error
    return value if isinstance(value, dict) else None


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


def _selected_events(store: FederationStore) -> tuple[set[str], set[str]]:
    resolved_members: set[str] = set()
    selected: set[str] = set()
    for resolution in store.resolutions():
        members = resolution.get("member_event_ids", [])
        selected_id = resolution.get("selected_event_id")
        if not isinstance(members, list) or not isinstance(selected_id, str):
            raise FederationError("resolution_record_invalid", "projection")
        resolved_members.update(members)
        selected.add(selected_id)
    return resolved_members, selected


def _projection_value(store: FederationStore) -> dict[str, Any]:
    events = store.events()
    by_id = {event.event_id: event for event in events}
    withdrawn = {event.withdraws for event in events if event.withdraws is not None}
    corrected = {
        event.correction_of for event in events if event.correction_of is not None
    }
    resolved_members, selected = _selected_events(store)
    conflicts = list(store.conflicts())
    resolved_conflict_ids = {
        resolution["conflict_id"] for resolution in store.resolutions()
    }

    candidate_fields: dict[tuple[str, str], list[tuple[FederatedEvent, Any]]] = {}
    subject_ids: set[str] = set()
    for event in events:
        if event.event_kind == "pmw.conflict.resolution":
            continue
        subject_ids.add(event.subject_ref)
        if (
            event.event_id in withdrawn
            or event.event_id in corrected
            or event.withdraws is not None
        ):
            continue
        payload = _payload_value(store, event)
        if payload is None or set(payload) != {"field", "value"}:
            continue
        field = payload["field"]
        if not isinstance(field, str) or not field:
            raise FederationError("projection_field_invalid", event.event_id)
        candidate_fields.setdefault((event.subject_ref, field), []).append(
            (event, payload["value"])
        )

    subjects: dict[str, dict[str, Any]] = {
        subject: {
            "fields": {},
            "unresolved_conflict_ids": [],
            "unresolved_event_ids": [],
        }
        for subject in sorted(subject_ids)
    }
    for conflict in conflicts:
        subject = conflict["subject_ref"]
        if subject in subjects and conflict["conflict_id"] not in resolved_conflict_ids:
            subjects[subject]["unresolved_conflict_ids"].append(conflict["conflict_id"])

    for (subject, field), candidates in sorted(candidate_fields.items()):
        active = candidates
        member_ids = {event.event_id for event, _ in active}
        if member_ids & resolved_members:
            active = [item for item in active if item[0].event_id in selected]
        chosen: tuple[FederatedEvent, Any] | None = None
        if len(active) == 1:
            chosen = active[0]
        elif active:
            for candidate in active:
                if all(
                    other[0].event_id == candidate[0].event_id
                    or _is_ancestor(by_id, other[0].event_id, candidate[0].event_id)
                    for other in active
                ):
                    chosen = candidate
                    break
        if chosen is None:
            subjects[subject]["unresolved_event_ids"].extend(
                sorted(event.event_id for event, _ in active)
            )
            continue
        subjects[subject]["fields"][field] = {
            "source_event_id": chosen[0].event_id,
            "value": chosen[1],
        }

    for subject in subjects.values():
        subject["unresolved_conflict_ids"] = sorted(
            set(subject["unresolved_conflict_ids"])
        )
        subject["unresolved_event_ids"] = sorted(set(subject["unresolved_event_ids"]))

    parent_ids = {parent for event in events for parent in event.causal_parents}
    return {
        "schema": PROJECTION_SCHEMA,
        "event_records": [
            {
                "event_id": event.event_id,
                "event_digest": event.core_digest,
                "event_kind": event.event_kind,
                "subject_ref": event.subject_ref,
                "fabric_payload_class": event.fabric_payload_class,
                "correction_of": event.correction_of,
                "withdraws": event.withdraws,
            }
            for event in events
        ],
        "causal_heads": sorted(
            event.event_id for event in events if event.event_id not in parent_ids
        ),
        "subjects": subjects,
        "conflicts": conflicts,
        "resolutions": list(store.resolutions()),
        "not_claimed": PROJECTION_NONCLAIMS,
    }


def rebuild_json(store: FederationStore) -> bytes:
    return canonical_bytes(_projection_value(store))


def rebuild_sqlite(store: FederationStore, path: str | Path) -> Path:
    target = Path(path)
    if target.exists():
        raise FederationError("projection_path_exists", str(target))
    target.parent.mkdir(parents=True, exist_ok=True)
    value = _projection_value(store)
    connection = sqlite3.connect(target)
    try:
        connection.executescript(
            """
            CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE events (
              event_id TEXT PRIMARY KEY,
              event_digest TEXT NOT NULL,
              event_kind TEXT NOT NULL,
              subject_ref TEXT NOT NULL,
              fabric_payload_class TEXT NOT NULL,
              correction_of TEXT,
              withdraws TEXT
            );
            CREATE TABLE fields (
              subject_ref TEXT NOT NULL,
              field_key TEXT NOT NULL,
              value_json TEXT NOT NULL,
              source_event_id TEXT NOT NULL,
              PRIMARY KEY (subject_ref, field_key)
            );
            CREATE TABLE unresolved_conflicts (
              conflict_id TEXT PRIMARY KEY,
              subject_ref TEXT NOT NULL
            );
            CREATE TABLE conflicts (
              conflict_id TEXT PRIMARY KEY,
              conflict_class TEXT NOT NULL,
              subject_ref TEXT NOT NULL,
              member_event_ids_json TEXT NOT NULL
            );
            CREATE TABLE resolutions (
              conflict_id TEXT NOT NULL,
              resolution_event_id TEXT PRIMARY KEY,
              selected_event_id TEXT NOT NULL
            );
            """
        )
        projection_digest = hashlib.sha256(canonical_bytes(value)).hexdigest()
        connection.executemany(
            "INSERT INTO meta(key,value) VALUES (?,?)",
            (("projection_digest", projection_digest), ("schema", PROJECTION_SCHEMA)),
        )
        connection.executemany(
            "INSERT INTO events VALUES (?,?,?,?,?,?,?)",
            [
                (
                    record["event_id"],
                    record["event_digest"],
                    record["event_kind"],
                    record["subject_ref"],
                    record["fabric_payload_class"],
                    record["correction_of"],
                    record["withdraws"],
                )
                for record in value["event_records"]
            ],
        )
        field_rows = []
        unresolved_rows = []
        for subject_ref, subject in sorted(value["subjects"].items()):
            for field_key, record in sorted(subject["fields"].items()):
                field_rows.append(
                    (
                        subject_ref,
                        field_key,
                        canonical_bytes(record["value"]).decode("utf-8"),
                        record["source_event_id"],
                    )
                )
            unresolved_rows.extend(
                (conflict_id, subject_ref)
                for conflict_id in subject["unresolved_conflict_ids"]
            )
        connection.executemany("INSERT INTO fields VALUES (?,?,?,?)", field_rows)
        connection.executemany(
            "INSERT INTO unresolved_conflicts VALUES (?,?)", unresolved_rows
        )
        connection.executemany(
            "INSERT INTO conflicts VALUES (?,?,?,?)",
            [
                (
                    record["conflict_id"],
                    record["conflict_class"],
                    record["subject_ref"],
                    canonical_bytes(record["member_event_ids"]).decode("utf-8"),
                )
                for record in value["conflicts"]
            ],
        )
        connection.executemany(
            "INSERT INTO resolutions VALUES (?,?,?)",
            [
                (
                    record["conflict_id"],
                    record["resolution_event_id"],
                    record["selected_event_id"],
                )
                for record in value["resolutions"]
            ],
        )
        connection.commit()
    except Exception:
        connection.close()
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    finally:
        if connection:
            connection.close()
    return target


def _compare(
    expected: Any,
    actual: Any,
    path: str,
    differences: list[ProjectionDifference],
) -> None:
    if type(expected) is not type(actual):
        differences.append(ProjectionDifference(path, "contradiction"))
        return
    if isinstance(expected, dict):
        for key in sorted(expected):
            child = f"{path}/{key}"
            if key not in actual:
                differences.append(ProjectionDifference(child, "contradiction"))
            else:
                _compare(expected[key], actual[key], child, differences)
        for key in sorted(set(actual) - set(expected)):
            differences.append(ProjectionDifference(f"{path}/{key}", "unmapped"))
        return
    if isinstance(expected, list):
        shared = min(len(expected), len(actual))
        for index in range(shared):
            _compare(expected[index], actual[index], f"{path}/{index}", differences)
        if len(actual) > len(expected):
            differences.extend(
                ProjectionDifference(f"{path}/{index}", "unmapped")
                for index in range(len(expected), len(actual))
            )
        elif len(expected) > len(actual):
            differences.extend(
                ProjectionDifference(f"{path}/{index}", "contradiction")
                for index in range(len(actual), len(expected))
            )
        return
    if expected != actual:
        differences.append(ProjectionDifference(path, "contradiction"))


def compare_projection(expected: Any, actual: Any) -> ProjectionComparison:
    differences: list[ProjectionDifference] = []
    _compare(expected, actual, "", differences)
    kinds = {difference.kind for difference in differences}
    if "contradiction" in kinds:
        status = "contradiction"
    elif "unmapped" in kinds:
        status = "unmapped"
    else:
        status = "expected_by_mapping"
    return ProjectionComparison(status, tuple(differences))
