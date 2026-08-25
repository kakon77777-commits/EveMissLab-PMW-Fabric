from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import threading
from typing import Any

from eml_wake.canonical import canonical_bytes, loads_strict
from eml_wake.errors import WakeError
from eml_wake.filesystem import publish_bytes_no_replace, publish_no_replace

from .causal import derive_heads
from .errors import FederationError
from .models import FederatedEvent, FederationConfig


def event_key(event_id: str) -> str:
    return hashlib.sha256(event_id.encode("utf-8")).hexdigest()


def replica_key(event: FederatedEvent) -> str:
    value = f"{event.replica_ref.replica_id}\x00{event.replica_ref.store_generation}"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def delivery_key(delivery_id: str) -> str:
    return hashlib.sha256(delivery_id.encode("utf-8")).hexdigest()


def _convert(error: WakeError) -> FederationError:
    return FederationError(error.code, error.message)


def _publish_json(path: Path, value: dict[str, Any]) -> None:
    try:
        publish_no_replace(path, value)
    except WakeError as error:
        raise _convert(error) from error


def _publish_bytes(path: Path, data: bytes) -> None:
    try:
        publish_bytes_no_replace(path, data)
    except WakeError as error:
        raise _convert(error) from error


def _read_object(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
        value = loads_strict(data)
    except OSError as error:
        raise FederationError("file_unreadable", str(path)) from error
    if not isinstance(value, dict):
        raise FederationError("contract_type_invalid", str(path))
    if data != canonical_bytes(value):
        raise FederationError("stored_record_not_canonical", str(path))
    return value


@dataclass(frozen=True)
class SubmissionResult:
    kind: str
    event_id: str
    delivery_id: str
    event_path: str
    payload_path: str
    duplicate_path: str | None = None


class FederationStore:
    def __init__(self, root: str | Path, config: FederationConfig):
        self.root = Path(root)
        self.config = config
        self.payloads_dir = self.root / "payloads"
        self.events_dir = self.root / "events"
        self.event_index_dir = self.root / "indexes" / "events"
        self.sequence_index_dir = self.root / "indexes" / "sequences"
        self.duplicates_dir = self.root / "duplicates"
        self.quarantine_dir = self.root / "quarantine"
        self.observations_dir = self.root / "observations"
        self.adoptions_dir = self.root / "adoptions"
        self.rejections_dir = self.root / "rejections"
        self.conflicts_dir = self.root / "conflicts"
        self.resolutions_dir = self.root / "resolutions"
        self.inventories_dir = self.root / "inventories"
        self._submit_lock = threading.RLock()
        for directory in (
            self.payloads_dir,
            self.events_dir,
            self.event_index_dir,
            self.sequence_index_dir,
            self.duplicates_dir,
            self.quarantine_dir,
            self.observations_dir,
            self.adoptions_dir,
            self.rejections_dir,
            self.conflicts_dir,
            self.resolutions_dir,
            self.inventories_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def payload_path(self, event: FederatedEvent) -> Path:
        return self.root.joinpath(*Path(event.payload_ref).parts)

    def event_path(self, event: FederatedEvent) -> Path:
        return (
            self.events_dir
            / replica_key(event)
            / f"{event.replica_seq:020d}-{event_key(event.event_id)}.json"
        )

    def event_index_path(self, event_id: str) -> Path:
        return self.event_index_dir / f"{event_key(event_id)}.json"

    def sequence_index_path(self, event: FederatedEvent) -> Path:
        return (
            self.sequence_index_dir
            / replica_key(event)
            / f"{event.replica_seq:020d}.json"
        )

    def duplicate_path(self, event_id: str, delivery_id: str) -> Path:
        return (
            self.duplicates_dir
            / event_key(event_id)
            / f"{delivery_key(delivery_id)}.json"
        )

    def _validate_submission(self, event: FederatedEvent, payload: bytes) -> None:
        if not isinstance(payload, bytes):
            raise FederationError("payload_type_invalid", event.event_id)
        if len(payload) > self.config.default_max_payload_bytes:
            raise FederationError("payload_too_large", event.event_id)
        try:
            text = payload.decode("utf-8", errors="strict")
        except UnicodeDecodeError as error:
            raise FederationError("payload_binary_unsupported", event.event_id) from error
        if any(ord(character) < 0x20 and character not in "\t\n\r" for character in text):
            raise FederationError("payload_binary_unsupported", event.event_id)
        actual = hashlib.sha256(payload).hexdigest().upper()
        if actual != event.payload_sha256:
            raise FederationError("payload_integrity_failed", event.event_id)
        expected_suffix = {
            "application/json": ".json",
            "text/markdown": ".md",
            "text/plain": ".txt",
        }[event.payload_media_type]
        if not event.payload_ref.endswith(expected_suffix):
            raise FederationError("payload_media_mismatch", event.event_id)
        if event.event_kind not in self.config.allowed_event_kinds:
            raise FederationError("event_kind_not_allowed", event.event_kind)
        if event.event_kind in self.config.authority_required_event_kinds:
            if event.authority_ref not in self.config.allowed_authority_refs:
                raise FederationError("authority_not_allowed", event.event_id)
        elif event.authority_ref is not None and event.authority_ref not in self.config.allowed_authority_refs:
            raise FederationError("authority_not_allowed", event.event_id)

    def _index_record(self, event: FederatedEvent, event_path: Path) -> dict[str, Any]:
        return {
            "schema": "pmw-federation-event-index/v1",
            "event_id": event.event_id,
            "core_digest": event.core_digest,
            "event_path": event_path.relative_to(self.root).as_posix(),
            "payload_ref": event.payload_ref,
            "payload_sha256": event.payload_sha256,
        }

    def _sequence_record(self, event: FederatedEvent, event_path: Path) -> dict[str, Any]:
        return {
            "schema": "pmw-federation-sequence-index/v1",
            "replica_id": event.replica_ref.replica_id,
            "store_generation": event.replica_ref.store_generation,
            "replica_seq": event.replica_seq,
            "event_id": event.event_id,
            "core_digest": event.core_digest,
            "event_path": event_path.relative_to(self.root).as_posix(),
        }

    def _quarantine(
        self,
        code: str,
        event: FederatedEvent,
        *,
        existing_digest: str | None,
        existing_event_id: str | None,
    ) -> None:
        record = {
            "schema": "pmw-federation-quarantine/v1",
            "code": code,
            "submitted_event_id": event.event_id,
            "submitted_core_digest": event.core_digest,
            "existing_event_id": existing_event_id,
            "existing_core_digest": existing_digest,
        }
        key = hashlib.sha256(canonical_bytes(record)).hexdigest()
        path = self.quarantine_dir / f"{key}.json"
        if path.exists():
            if _read_object(path) != record:
                raise FederationError("quarantine_content_collision", event.event_id)
            return
        _publish_json(path, record)

    def _record_duplicate(
        self, event: FederatedEvent, delivery_id: str, event_path: Path, payload_path: Path
    ) -> SubmissionResult:
        duplicate_path = self.duplicate_path(event.event_id, delivery_id)
        record = {
            "schema": "pmw-federation-duplicate/v1",
            "event_id": event.event_id,
            "delivery_id": delivery_id,
            "core_digest": event.core_digest,
        }
        if not duplicate_path.exists():
            _publish_json(duplicate_path, record)
        elif _read_object(duplicate_path) != record:
            raise FederationError("duplicate_content_collision", event.event_id)
        return SubmissionResult(
            "duplicate",
            event.event_id,
            delivery_id,
            str(event_path),
            str(payload_path),
            str(duplicate_path),
        )

    def submit(
        self, event: FederatedEvent, payload: bytes, *, delivery_id: str
    ) -> SubmissionResult:
        if not isinstance(event, FederatedEvent):
            raise FederationError("event_type_invalid", "submit")
        if not isinstance(delivery_id, str) or not delivery_id:
            raise FederationError("delivery_id_invalid", event.event_id)
        self._validate_submission(event, payload)
        payload_path = self.payload_path(event)
        event_path = self.event_path(event)
        index_path = self.event_index_path(event.event_id)
        sequence_path = self.sequence_index_path(event)

        with self._submit_lock:
            if index_path.exists():
                existing_index = _read_object(index_path)
                existing_digest = existing_index.get("core_digest")
                existing_event_id = existing_index.get("event_id")
                if existing_digest != event.core_digest:
                    self._quarantine(
                        "event_content_collision",
                        event,
                        existing_digest=existing_digest,
                        existing_event_id=existing_event_id,
                    )
                    raise FederationError("event_content_collision", event.event_id)
                existing_event = self.get_event(event.event_id)
                if existing_event != event or payload_path.read_bytes() != payload:
                    raise FederationError("stored_event_integrity_failed", event.event_id)
                return self._record_duplicate(
                    event, delivery_id, event_path, payload_path
                )

            if sequence_path.exists():
                owner = _read_object(sequence_path)
                if owner.get("event_id") != event.event_id or owner.get("core_digest") != event.core_digest:
                    self._quarantine(
                        "replica_sequence_collision",
                        event,
                        existing_digest=owner.get("core_digest"),
                        existing_event_id=owner.get("event_id"),
                    )
                    raise FederationError("replica_sequence_collision", event.event_id)

            if payload_path.exists():
                if payload_path.read_bytes() != payload:
                    raise FederationError("payload_integrity_failed", event.event_id)
            else:
                try:
                    _publish_bytes(payload_path, payload)
                except FederationError as error:
                    if error.code != "immutable_file_exists":
                        raise
                    if not payload_path.is_file() or payload_path.read_bytes() != payload:
                        raise FederationError(
                            "payload_integrity_failed", event.event_id
                        ) from error

            created_event = False
            if event_path.exists():
                existing = _read_object(event_path)
                if existing != event.to_dict():
                    self._quarantine(
                        "event_content_collision",
                        event,
                        existing_digest=None,
                        existing_event_id=existing.get("event_id"),
                    )
                    raise FederationError("event_content_collision", event.event_id)
            else:
                try:
                    _publish_json(event_path, event.to_dict())
                    created_event = True
                except FederationError as error:
                    if error.code != "immutable_file_exists":
                        raise
                    if not event_path.is_file() or _read_object(event_path) != event.to_dict():
                        raise FederationError(
                            "event_content_collision", event.event_id
                        ) from error

            sequence_record = self._sequence_record(event, event_path)
            if sequence_path.exists():
                owner = _read_object(sequence_path)
                if owner != sequence_record:
                    self._quarantine(
                        "replica_sequence_collision",
                        event,
                        existing_digest=owner.get("core_digest"),
                        existing_event_id=owner.get("event_id"),
                    )
                    raise FederationError("replica_sequence_collision", event.event_id)
            else:
                try:
                    _publish_json(sequence_path, sequence_record)
                except FederationError as error:
                    if error.code != "immutable_file_exists":
                        raise
                    owner = _read_object(sequence_path)
                    if owner != sequence_record:
                        self._quarantine(
                            "replica_sequence_collision",
                            event,
                            existing_digest=owner.get("core_digest"),
                            existing_event_id=owner.get("event_id"),
                        )
                        raise FederationError(
                            "replica_sequence_collision", event.event_id
                        ) from error

            index_record = self._index_record(event, event_path)
            if index_path.exists():
                existing_index = _read_object(index_path)
                if existing_index != index_record:
                    self._quarantine(
                        "event_content_collision",
                        event,
                        existing_digest=existing_index.get("core_digest"),
                        existing_event_id=existing_index.get("event_id"),
                    )
                    raise FederationError("event_content_collision", event.event_id)
            else:
                try:
                    _publish_json(index_path, index_record)
                except FederationError as error:
                    if error.code != "immutable_file_exists":
                        raise
                    existing_index = _read_object(index_path)
                    if existing_index != index_record:
                        self._quarantine(
                            "event_content_collision",
                            event,
                            existing_digest=existing_index.get("core_digest"),
                            existing_event_id=existing_index.get("event_id"),
                        )
                        raise FederationError(
                            "event_content_collision", event.event_id
                        ) from error

            if not created_event:
                return self._record_duplicate(
                    event, delivery_id, event_path, payload_path
                )
            return SubmissionResult(
                "created",
                event.event_id,
                delivery_id,
                str(event_path),
                str(payload_path),
            )

    def get_event(self, event_id: str) -> FederatedEvent:
        index_path = self.event_index_path(event_id)
        if not index_path.is_file():
            raise FederationError("event_not_found", event_id)
        index = _read_object(index_path)
        if index.get("event_id") != event_id:
            raise FederationError("event_index_mismatch", event_id)
        relative = index.get("event_path")
        if not isinstance(relative, str) or not relative:
            raise FederationError("event_index_invalid", event_id)
        event_path = self.root.joinpath(*Path(relative).parts)
        event = FederatedEvent.from_dict(_read_object(event_path))
        if event.event_id != event_id or event.core_digest != index.get("core_digest"):
            raise FederationError("stored_event_integrity_failed", event_id)
        payload_path = self.payload_path(event)
        try:
            payload = payload_path.read_bytes()
        except OSError as error:
            raise FederationError("payload_unreadable", event_id) from error
        if hashlib.sha256(payload).hexdigest().upper() != event.payload_sha256:
            raise FederationError("payload_integrity_failed", event_id)
        return event

    def events(self) -> tuple[FederatedEvent, ...]:
        items = [
            self.get_event(_read_object(path)["event_id"])
            for path in sorted(self.event_index_dir.glob("*.json"))
        ]
        return tuple(
            sorted(
                items,
                key=lambda event: (
                    event.replica_ref.realm_id,
                    event.replica_ref.replica_id,
                    event.replica_ref.store_generation,
                    event.replica_seq,
                    event.event_id,
                ),
            )
        )

    def heads(self) -> tuple[str, ...]:
        return derive_heads(self.events())
