from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import re
from typing import Any

from eml_wake.canonical import canonical_bytes, loads_strict
from eml_wake.errors import WakeError
from eml_pmw.federation.models import (
    FederatedEvent,
    RealmRef,
    ReplicaRef,
    REQUIRED_NONCLAIMS,
)

from .canonical import profile_digest
from .errors import RelationContractError
from .events import EVENT_KINDS, RelationContractEvent
from .models_common import validate_digest_ref
from .references import validate_portable_ref
from .store import RelationContractStore


CTCL = re.compile(r"^ctcl:instant:[0-9a-f-]{36}$", re.IGNORECASE)
HEX64_UPPER = re.compile(r"^[0-9A-F]{64}$")
ADOPTION_NONCLAIMS = (
    "acceptance_created",
    "authority_granted",
    "execution_observed",
    "resident_identity_continuity",
)
ADOPTION_FIELDS = {
    "schema",
    "adoption_id",
    "event_id",
    "envelope_digest",
    "relation_event_digest",
    "payload_sha256",
    "receiver_realm_id",
    "decision",
    "receiver_observation_refs",
    "not_claimed",
    "receipt_digest",
}
STATE_FIELDS = {
    "schema",
    "adoption_id",
    "receipt_digest",
    "observation_digest",
    "event_id",
    "relation_event_digest",
    "status",
    "missing_parent_ids",
    "missing_object_digests",
    "reason_codes",
    "record_digest",
}


@dataclass(frozen=True)
class ImportedRelationObservation:
    envelope: FederatedEvent
    relation_event: RelationContractEvent
    envelope_digest: str
    payload_sha256: str
    fabric_payload_class: str
    observation_digest: str


@dataclass(frozen=True)
class ExplicitRelationAdoptionReceipt:
    schema: str
    adoption_id: str
    event_id: str
    envelope_digest: str
    relation_event_digest: str
    payload_sha256: str
    receiver_realm_id: str
    decision: str
    receiver_observation_refs: tuple[str, ...]
    not_claimed: tuple[str, ...]
    receipt_digest: str

    @staticmethod
    def digest_for(value: dict[str, Any]) -> str:
        core = {key: item for key, item in value.items() if key != "receipt_digest"}
        return profile_digest({"kind": "relation-event-adoption-receipt", **core})

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ExplicitRelationAdoptionReceipt":
        if not isinstance(value, dict) or set(value) != ADOPTION_FIELDS:
            raise RelationContractError("adoption_receipt_invalid", "fields")
        refs = value["receiver_observation_refs"]
        not_claimed = value["not_claimed"]
        if (
            value["schema"] != "arcp/relation-event-adoption-receipt/0.1"
            or value["decision"] != "adopted"
            or not isinstance(refs, list)
            or not refs
            or len(refs) != len(set(refs))
            or not isinstance(not_claimed, list)
            or tuple(not_claimed) != ADOPTION_NONCLAIMS
            or not HEX64_UPPER.fullmatch(str(value["payload_sha256"]))
        ):
            raise RelationContractError("adoption_receipt_invalid", "value")
        for ref in refs:
            validate_portable_ref(ref, "receiver_observation_refs")
        for field in ("adoption_id", "event_id", "receiver_realm_id"):
            validate_portable_ref(value[field], field)
        for field in ("envelope_digest", "relation_event_digest", "receipt_digest"):
            validate_digest_ref(value[field], field)
        if value["receipt_digest"] != cls.digest_for(value):
            raise RelationContractError(
                "adoption_receipt_digest_mismatch", value["adoption_id"]
            )
        return cls(
            value["schema"],
            value["adoption_id"],
            value["event_id"],
            value["envelope_digest"],
            value["relation_event_digest"],
            value["payload_sha256"],
            value["receiver_realm_id"],
            value["decision"],
            tuple(refs),
            tuple(not_claimed),
            value["receipt_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["receiver_observation_refs"] = list(self.receiver_observation_refs)
        value["not_claimed"] = list(self.not_claimed)
        return value


@dataclass(frozen=True)
class AdoptionResult:
    status: str
    adoption_id: str
    event_id: str
    missing_parent_ids: tuple[str, ...]
    missing_object_digests: tuple[str, ...]
    record_path: str


@dataclass(frozen=True)
class AdoptionHistoryVerification:
    status: str
    error_codes: tuple[str, ...]
    pending_count: int
    adopted_count: int
    quarantine_count: int


def wrap_relation_event(
    event: RelationContractEvent,
    *,
    realm_ref: RealmRef,
    replica_ref: ReplicaRef,
    replica_seq: int,
    payload_class: str,
) -> tuple[FederatedEvent, bytes]:
    if not isinstance(event, RelationContractEvent):
        raise RelationContractError("relation_event_invalid", "event")
    if payload_class not in {"P0", "P1"}:
        raise RelationContractError("fabric_payload_class_invalid", payload_class)
    payload = canonical_bytes(event.to_dict())
    payload_hash = hashlib.sha256(payload).hexdigest()
    is_registered = (
        event.created_time.verification_status == "verified"
        and CTCL.fullmatch(event.created_time.instant_ref) is not None
    )
    envelope = FederatedEvent.from_dict(
        {
            "schema": "pmw-federated-event/v1",
            "event_id": event.event_id,
            "event_kind": event.event_kind,
            "subject_ref": event.subject_ref,
            "realm_ref": {
                **asdict(realm_ref),
                "evidence_refs": list(realm_ref.evidence_refs),
            },
            "replica_ref": {
                **asdict(replica_ref),
                "evidence_refs": list(replica_ref.evidence_refs),
            },
            "replica_seq": replica_seq,
            "causal_parents": list(event.causal_parents),
            "claimed_actor_ref": event.claimed_actor_ref,
            "claimed_instance_ref": None,
            "authority_ref": event.lifecycle_transition_authority_ref,
            "payload_ref": f"payloads/relation-contract-{payload_hash}.json",
            "payload_sha256": payload_hash.upper(),
            "payload_media_type": "application/json",
            "fabric_payload_class": payload_class,
            "created_time_ref": (
                event.created_time.instant_ref if is_registered else None
            ),
            "temporal_evidence_status": (
                "registered_anchor" if is_registered else "unmeasured"
            ),
            "local_recorded_at": event.local_recorded_at,
            "correction_of": event.correction_of,
            "withdraws": event.withdraws,
            "not_claimed": sorted(REQUIRED_NONCLAIMS),
        }
    )
    return envelope, payload


def _observation_digest(
    envelope: FederatedEvent,
    event: RelationContractEvent,
    payload_sha256: str,
) -> str:
    return profile_digest(
        {
            "kind": "imported-relation-observation",
            "envelope_digest": envelope.core_digest,
            "relation_event_digest": event.event_digest,
            "payload_sha256": payload_sha256,
            "fabric_payload_class": envelope.fabric_payload_class,
        }
    )


def inspect_imported_relation_event(
    federated_event: FederatedEvent, payload: bytes
) -> ImportedRelationObservation:
    if not isinstance(federated_event, FederatedEvent):
        raise RelationContractError("relation_envelope_invalid", "event")
    if federated_event.event_kind not in EVENT_KINDS:
        raise RelationContractError(
            "relation_event_kind_invalid", federated_event.event_kind
        )
    if (
        not isinstance(payload, bytes)
        or federated_event.payload_media_type != "application/json"
        or hashlib.sha256(payload).hexdigest().upper()
        != federated_event.payload_sha256
    ):
        raise RelationContractError(
            "relation_envelope_payload_mismatch", federated_event.event_id
        )
    try:
        value = loads_strict(payload)
    except WakeError as error:
        raise RelationContractError(
            "relation_payload_invalid", federated_event.event_id
        ) from error
    if not isinstance(value, dict) or payload != canonical_bytes(value):
        raise RelationContractError(
            "relation_payload_not_canonical", federated_event.event_id
        )
    event = RelationContractEvent.from_dict(value)
    if (
        federated_event.event_id != event.event_id
        or federated_event.event_kind != event.event_kind
        or federated_event.subject_ref != event.subject_ref
        or federated_event.causal_parents != event.causal_parents
        or federated_event.claimed_actor_ref != event.claimed_actor_ref
        or federated_event.claimed_instance_ref is not None
        or federated_event.authority_ref
        != event.lifecycle_transition_authority_ref
        or federated_event.correction_of != event.correction_of
        or federated_event.withdraws != event.withdraws
    ):
        raise RelationContractError(
            "relation_envelope_event_mismatch", federated_event.event_id
        )
    payload_sha256 = hashlib.sha256(payload).hexdigest().upper()
    return ImportedRelationObservation(
        federated_event,
        event,
        federated_event.core_digest,
        payload_sha256,
        federated_event.fabric_payload_class,
        _observation_digest(federated_event, event, payload_sha256),
    )


def _record_digest(value: dict[str, Any]) -> str:
    core = {key: item for key, item in value.items() if key != "record_digest"}
    return profile_digest({"kind": "relation-adoption-state", **core})


def _adoption_key(adoption_id: str) -> str:
    return hashlib.sha256(adoption_id.encode("utf-8")).hexdigest()


def _record_path(store: RelationContractStore, status: str, adoption_id: str) -> Path:
    directory = {
        "pending_dependencies": store.adoptions_pending_dir,
        "adopted": store.adoptions_adopted_dir,
        "quarantined": store.adoptions_quarantine_dir,
    }[status]
    return directory / f"{_adoption_key(adoption_id)}.json"


def _state_record(
    receipt: ExplicitRelationAdoptionReceipt,
    observation: ImportedRelationObservation,
    *,
    status: str,
    missing_parent_ids: tuple[str, ...] = (),
    missing_object_digests: tuple[str, ...] = (),
    reason_codes: tuple[str, ...] = (),
) -> dict[str, Any]:
    value = {
        "schema": "arcp/relation-event-adoption-state/0.1",
        "adoption_id": receipt.adoption_id,
        "receipt_digest": receipt.receipt_digest,
        "observation_digest": observation.observation_digest,
        "event_id": observation.relation_event.event_id,
        "relation_event_digest": observation.relation_event.event_digest,
        "status": status,
        "missing_parent_ids": list(missing_parent_ids),
        "missing_object_digests": list(missing_object_digests),
        "reason_codes": list(reason_codes),
        "record_digest": "",
    }
    value["record_digest"] = _record_digest(value)
    return value


def _read_state_record(
    store: RelationContractStore, path: Path, expected_status: str
) -> dict[str, Any]:
    value = store._read_store_record(path)
    if (
        set(value) != STATE_FIELDS
        or value.get("schema") != "arcp/relation-event-adoption-state/0.1"
        or value.get("status") != expected_status
        or value.get("record_digest") != _record_digest(value)
        or path.name != f"{_adoption_key(str(value.get('adoption_id')))}.json"
    ):
        raise RelationContractError("adoption_record_invalid", str(path))
    for field in ("missing_parent_ids", "missing_object_digests", "reason_codes"):
        items = value.get(field)
        if (
            not isinstance(items, list)
            or len(items) != len(set(items))
            or any(not isinstance(item, str) or not item for item in items)
        ):
            raise RelationContractError("adoption_record_invalid", str(path))
    return value


def _publish_state_record(
    store: RelationContractStore, value: dict[str, Any]
) -> Path:
    path = _record_path(store, str(value["status"]), str(value["adoption_id"]))
    if path.exists():
        existing = _read_state_record(store, path, str(value["status"]))
        if existing != value:
            raise RelationContractError(
                "adoption_id_collision", str(value["adoption_id"])
            )
        return path
    try:
        store._publish_store_record(path, value)
    except RelationContractError as error:
        if error.code != "immutable_file_exists":
            raise
        existing = _read_state_record(store, path, str(value["status"]))
        if existing != value:
            raise RelationContractError(
                "adoption_id_collision", str(value["adoption_id"])
            ) from error
    return path


def _validated_receipt(
    receipt: ExplicitRelationAdoptionReceipt,
) -> ExplicitRelationAdoptionReceipt:
    if not isinstance(receipt, ExplicitRelationAdoptionReceipt):
        raise RelationContractError("adoption_receipt_invalid", "receipt")
    return ExplicitRelationAdoptionReceipt.from_dict(receipt.to_dict())


def _observation_valid(observation: ImportedRelationObservation) -> bool:
    if not isinstance(observation, ImportedRelationObservation):
        return False
    payload = canonical_bytes(observation.relation_event.to_dict())
    payload_sha256 = hashlib.sha256(payload).hexdigest().upper()
    try:
        expected = inspect_imported_relation_event(observation.envelope, payload)
    except RelationContractError:
        return False
    return (
        observation.payload_sha256 == payload_sha256
        and observation.envelope_digest == expected.envelope_digest
        and observation.fabric_payload_class == expected.fabric_payload_class
        and observation.observation_digest == expected.observation_digest
    )


def _receipt_matches_observation(
    receipt: ExplicitRelationAdoptionReceipt,
    observation: ImportedRelationObservation,
) -> bool:
    return (
        receipt.event_id == observation.relation_event.event_id
        and receipt.envelope_digest == observation.envelope_digest
        and receipt.relation_event_digest == observation.relation_event.event_digest
        and receipt.payload_sha256 == observation.payload_sha256
    )


def adopt_relation_event(
    observation: ImportedRelationObservation,
    explicit_adoption_receipt: ExplicitRelationAdoptionReceipt,
    local_store: RelationContractStore,
) -> AdoptionResult:
    if not isinstance(local_store, RelationContractStore):
        raise RelationContractError("adoption_store_invalid", "store")
    receipt = _validated_receipt(explicit_adoption_receipt)
    quarantine_path = _record_path(
        local_store, "quarantined", receipt.adoption_id
    )
    if quarantine_path.exists():
        existing = _read_state_record(
            local_store, quarantine_path, "quarantined"
        )
        if (
            not _observation_valid(observation)
            and existing["receipt_digest"] == receipt.receipt_digest
            and existing["observation_digest"] == observation.observation_digest
        ):
            return AdoptionResult(
                "quarantined",
                receipt.adoption_id,
                observation.relation_event.event_id,
                (),
                (),
                str(quarantine_path),
            )
        raise RelationContractError(
            "adoption_id_quarantined", receipt.adoption_id
        )
    adopted_path = _record_path(local_store, "adopted", receipt.adoption_id)
    if adopted_path.exists():
        existing = _read_state_record(local_store, adopted_path, "adopted")
        if (
            existing["receipt_digest"] != receipt.receipt_digest
            or not _observation_valid(observation)
            or existing["observation_digest"] != observation.observation_digest
        ):
            raise RelationContractError("adoption_id_collision", receipt.adoption_id)
        return AdoptionResult(
            "adopted",
            receipt.adoption_id,
            observation.relation_event.event_id,
            (),
            (),
            str(adopted_path),
        )

    if not _observation_valid(observation) or not _receipt_matches_observation(
        receipt, observation
    ):
        record = _state_record(
            receipt,
            observation,
            status="quarantined",
            reason_codes=("adoption_integrity_failed",),
        )
        path = _publish_state_record(local_store, record)
        return AdoptionResult(
            "quarantined",
            receipt.adoption_id,
            observation.relation_event.event_id,
            (),
            (),
            str(path),
        )

    known_ids = {item.event_id for item in local_store.events()}
    missing_parents = tuple(
        sorted(set(observation.relation_event.causal_parents) - known_ids)
    )
    missing_objects: tuple[str, ...] = ()
    try:
        local_store.get_object(observation.relation_event.object_digest)
    except RelationContractError as error:
        if error.code != "object_not_found":
            raise
        missing_objects = (observation.relation_event.object_digest,)
    if missing_parents or missing_objects:
        record = _state_record(
            receipt,
            observation,
            status="pending_dependencies",
            missing_parent_ids=missing_parents,
            missing_object_digests=missing_objects,
            reason_codes=("adoption_dependencies_missing",),
        )
        path = _publish_state_record(local_store, record)
        return AdoptionResult(
            "pending_dependencies",
            receipt.adoption_id,
            observation.relation_event.event_id,
            missing_parents,
            missing_objects,
            str(path),
        )

    pending_path = _record_path(
        local_store, "pending_dependencies", receipt.adoption_id
    )
    if pending_path.exists():
        pending = _read_state_record(
            local_store, pending_path, "pending_dependencies"
        )
        if (
            pending["receipt_digest"] != receipt.receipt_digest
            or pending["observation_digest"] != observation.observation_digest
        ):
            raise RelationContractError("adoption_id_collision", receipt.adoption_id)
    try:
        local_store.append_event(observation.relation_event)
    except RelationContractError as error:
        record = _state_record(
            receipt,
            observation,
            status="quarantined",
            reason_codes=(error.code,),
        )
        path = _publish_state_record(local_store, record)
        return AdoptionResult(
            "quarantined",
            receipt.adoption_id,
            observation.relation_event.event_id,
            (),
            (),
            str(path),
        )
    adopted = _state_record(
        receipt, observation, status="adopted"
    )
    path = _publish_state_record(local_store, adopted)
    return AdoptionResult(
        "adopted",
        receipt.adoption_id,
        observation.relation_event.event_id,
        (),
        (),
        str(path),
    )


def verify_adoption_history(
    store: RelationContractStore,
) -> AdoptionHistoryVerification:
    errors: list[str] = []
    counts: dict[str, int] = {}
    directories = {
        "pending_dependencies": store.adoptions_pending_dir,
        "adopted": store.adoptions_adopted_dir,
        "quarantined": store.adoptions_quarantine_dir,
    }
    records: dict[tuple[str, str], dict[str, Any]] = {}
    events_by_id = {event.event_id: event for event in store.events()}
    for status, directory in directories.items():
        entries = sorted(directory.iterdir())
        counts[status] = len(entries)
        for path in entries:
            if not path.is_file() or path.suffix != ".json":
                errors.append("adoption_record_invalid")
                continue
            try:
                value = _read_state_record(store, path, status)
                key = (str(value["adoption_id"]), status)
                if key in records:
                    errors.append("adoption_record_invalid")
                records[key] = value
            except RelationContractError:
                errors.append("adoption_record_invalid")
    for (adoption_id, _status), value in records.items():
        pending = records.get((adoption_id, "pending_dependencies"))
        adopted = records.get((adoption_id, "adopted"))
        quarantined = records.get((adoption_id, "quarantined"))
        if pending is not None and adopted is not None and (
            pending["receipt_digest"] != adopted["receipt_digest"]
            or pending["observation_digest"] != adopted["observation_digest"]
        ):
            errors.append("adoption_history_conflict")
        if quarantined is not None and (
            pending is not None or adopted is not None
        ):
            errors.append("adoption_history_conflict")
        if value["status"] == "adopted":
            event = events_by_id.get(str(value["event_id"]))
            if event is None:
                errors.append("adoption_history_event_missing")
            elif event.event_digest != value["relation_event_digest"]:
                errors.append("adoption_history_event_mismatch")
    error_codes = tuple(sorted(set(errors)))
    return AdoptionHistoryVerification(
        "invalid" if error_codes else "verified",
        error_codes,
        counts.get("pending_dependencies", 0),
        counts.get("adopted", 0),
        counts.get("quarantined", 0),
    )
