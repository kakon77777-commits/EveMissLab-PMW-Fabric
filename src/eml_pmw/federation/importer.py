from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

from eml_wake.canonical import canonical_bytes, loads_strict

from .causal import validate_graph
from .errors import FederationError
from .models import FederatedEvent
from .store import FederationStore


CTCL = re.compile(r"^ctcl:instant:[0-9a-f-]{36}$", re.IGNORECASE)
OBSERVER_FIELDS = {
    "observer_id",
    "realm_id",
    "method",
    "observed_origin",
    "observed_time_ref",
    "advertised_missing_parent_ids",
}


@dataclass(frozen=True)
class ImportResult:
    status: str
    event_id: str
    missing_parent_ids: tuple[str, ...]
    observation_path: str


def _validate_observer(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FederationError("observer_type_invalid", "observer")
    unknown = sorted(set(value) - OBSERVER_FIELDS)
    missing = sorted(OBSERVER_FIELDS - set(value))
    if unknown:
        raise FederationError("observer_unknown_field", unknown[0])
    if missing:
        raise FederationError("observer_missing_field", missing[0])
    for field in ("observer_id", "realm_id", "method"):
        if not isinstance(value[field], str) or not value[field]:
            raise FederationError("observer_field_invalid", field)
    if value["method"] not in {"local_file_read", "provider_adapter", "fixture"}:
        raise FederationError("observer_method_invalid", value["method"])
    if value["observed_origin"] is not None and (
        not isinstance(value["observed_origin"], str) or not value["observed_origin"]
    ):
        raise FederationError("observed_origin_invalid", value["observer_id"])
    if value["observed_time_ref"] is not None and (
        not isinstance(value["observed_time_ref"], str)
        or not CTCL.fullmatch(value["observed_time_ref"])
    ):
        raise FederationError("observed_time_ref_invalid", value["observer_id"])
    advertised = value["advertised_missing_parent_ids"]
    if (
        not isinstance(advertised, list)
        or any(not isinstance(item, str) or not item for item in advertised)
        or len(advertised) != len(set(advertised))
    ):
        raise FederationError("advertised_parent_ids_invalid", value["observer_id"])
    return value


def import_event(
    store: FederationStore,
    event_bytes: bytes,
    payload_bytes: bytes,
    observer: dict[str, Any],
) -> ImportResult:
    receiver = _validate_observer(observer)
    try:
        raw = loads_strict(event_bytes)
    except Exception as error:
        raise FederationError("event_input_invalid", "event bytes") from error
    if not isinstance(raw, dict):
        raise FederationError("event_input_invalid", "event bytes")
    if event_bytes != canonical_bytes(raw):
        raise FederationError("event_not_canonical", raw.get("event_id", "event"))
    event = FederatedEvent.from_dict(raw)
    if hashlib.sha256(payload_bytes).hexdigest().upper() != event.payload_sha256:
        raise FederationError("payload_integrity_failed", event.event_id)

    validation = validate_graph((*store.events(), event))
    if validation.code in {
        "causal_cycle",
        "replica_sequence_collision",
        "event_content_collision",
    }:
        store.quarantine_event(validation.code, event)
        raise FederationError(validation.code, event.event_id)
    missing = validation.missing_parent_ids
    advertised = set(receiver["advertised_missing_parent_ids"])
    if not set(missing) <= advertised:
        raise FederationError("missing_parent_not_advertised", event.event_id)

    submission = store.submit(
        event,
        payload_bytes,
        delivery_id=f"import:{receiver['observer_id']}:{event.event_id}",
    )
    status = "pending_dependencies" if missing else (
        "duplicate" if submission.kind == "duplicate" else "imported"
    )
    record = {
        "schema": "pmw-federation-import-observation/v1",
        "event_id": event.event_id,
        "event_digest": event.core_digest,
        "observer_id": receiver["observer_id"],
        "observer_realm_id": receiver["realm_id"],
        "method": receiver["method"],
        "observed_origin": receiver["observed_origin"],
        "observed_time_ref": receiver["observed_time_ref"],
        "status": status,
        "missing_parent_ids": list(missing),
        "not_claimed": [
            "sender_authorship_verified",
            "resident_identity_continuity",
            "remote_adoption",
            "authority_to_execute",
        ],
    }
    path = store.record_observation(event.event_id, receiver["observer_id"], record)
    return ImportResult(status, event.event_id, missing, str(path))
