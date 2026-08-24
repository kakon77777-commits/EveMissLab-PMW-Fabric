from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from eml_wake.errors import WakeError
from eml_wake.filesystem import (
    publish_bytes_no_replace,
    publish_no_replace,
    read_canonical_file,
)

from .canonical import digest_ref
from .errors import HandoffError
from .filesystem import PayloadSnapshot
from .models import HandoffConfig, HandoffEnvelope


def handoff_key(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _convert(error: WakeError) -> HandoffError:
    return HandoffError(error.code, error.message, details=error.details)


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


def _read_json(path: Path) -> dict[str, Any]:
    try:
        return read_canonical_file(path)
    except WakeError as error:
        raise _convert(error) from error


@dataclass(frozen=True)
class SubmissionResult:
    kind: str
    handoff_id: str
    delivery_id: str
    envelope_path: str
    payload_path: str
    duplicate_path: str | None = None


class HandoffStore:
    def __init__(self, root: str | Path, config: HandoffConfig):
        self.root = Path(root)
        self.config = config
        self.payloads_dir = self.root / "payloads"
        self.envelopes_dir = self.root / "envelopes"
        self.claims_dir = self.root / "claims"
        self.materializations_dir = self.root / "materializations"
        self.receipts_dir = self.root / "receipts"
        self.failures_dir = self.root / "failures"
        self.duplicates_dir = self.root / "duplicates"
        self.notifications_dir = self.root / "notifications"
        self.corrections_dir = self.root / "corrections"
        self.quarantine_dir = self.root / "quarantine"
        for directory in (
            self.payloads_dir,
            self.envelopes_dir,
            self.claims_dir,
            self.materializations_dir,
            self.receipts_dir,
            self.failures_dir,
            self.duplicates_dir,
            self.notifications_dir,
            self.corrections_dir,
            self.quarantine_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def envelope_path(self, handoff_id: str) -> Path:
        return self.envelopes_dir / f"{handoff_key(handoff_id)}.json"

    def payload_path(self, envelope: HandoffEnvelope) -> Path:
        return self.root.joinpath(*Path(envelope.payload_ref).parts)

    def duplicate_path(self, handoff_id: str, delivery_id: str) -> Path:
        return (
            self.duplicates_dir
            / handoff_key(handoff_id)
            / f"{handoff_key(delivery_id)}.json"
        )

    def quarantine_path(self, envelope: HandoffEnvelope) -> Path:
        key = handoff_key(
            f"{envelope.handoff_id}\0{envelope.delivery_id}\0{envelope.core_digest}"
        )
        return self.quarantine_dir / f"{key}.json"

    def get_envelope(self, handoff_id: str) -> HandoffEnvelope:
        path = self.envelope_path(handoff_id)
        if not path.is_file():
            raise HandoffError("handoff_not_found", handoff_id)
        envelope = HandoffEnvelope.from_dict(_read_json(path))
        if envelope.handoff_id != handoff_id:
            raise HandoffError("handoff_filename_mismatch", handoff_id)
        return envelope

    def _verify_submission(
        self, envelope: HandoffEnvelope, snapshot: PayloadSnapshot
    ) -> Path:
        if envelope.target_kind not in self.config.allowed_target_kinds:
            raise HandoffError("target_kind_not_allowed", envelope.target_kind)
        if envelope.authority_ref not in self.config.allowed_authority_refs:
            raise HandoffError("authority_not_allowed", envelope.authority_ref)
        expected_ref = f"payloads/{handoff_key(envelope.handoff_id)}{snapshot.extension}"
        if envelope.payload_ref != expected_ref:
            raise HandoffError("payload_ref_mismatch", expected_ref)
        if envelope.payload_sha256 != snapshot.sha256:
            raise HandoffError("payload_integrity_failed", "payload SHA-256 mismatch")
        if envelope.payload_bytes != snapshot.byte_count:
            raise HandoffError("payload_size_mismatch", "payload byte count mismatch")
        if envelope.payload_media_type != snapshot.media_type:
            raise HandoffError("payload_media_mismatch", "payload media type mismatch")
        return self.payload_path(envelope)

    def _quarantine_collision(
        self, existing: HandoffEnvelope, submitted: HandoffEnvelope
    ) -> None:
        record = {
            "schema_version": "eml-handoff/quarantine-0.1",
            "handoff_id": submitted.handoff_id,
            "delivery_id": submitted.delivery_id,
            "existing_core_digest": existing.core_digest,
            "submitted_core_digest": submitted.core_digest,
            "observed_at": _now_iso(),
            "code": "handoff_content_collision",
        }
        path = self.quarantine_path(submitted)
        if not path.exists():
            _publish_json(path, record)

    def submit(
        self, envelope: HandoffEnvelope, snapshot: PayloadSnapshot
    ) -> SubmissionResult:
        payload_path = self._verify_submission(envelope, snapshot)
        envelope_path = self.envelope_path(envelope.handoff_id)
        if envelope_path.exists():
            existing = self.get_envelope(envelope.handoff_id)
            if existing.core_digest != envelope.core_digest:
                self._quarantine_collision(existing, envelope)
                raise HandoffError(
                    "handoff_content_collision",
                    "same handoff_id was submitted with different core content",
                    details={
                        "existing": existing.core_digest,
                        "submitted": envelope.core_digest,
                    },
                )
            if not payload_path.is_file() or payload_path.read_bytes() != snapshot.data:
                raise HandoffError(
                    "payload_integrity_failed", "stored payload does not match duplicate"
                )
            duplicate_path = self.duplicate_path(
                envelope.handoff_id, envelope.delivery_id
            )
            record = {
                "schema_version": "eml-handoff/duplicate-0.1",
                "handoff_id": envelope.handoff_id,
                "delivery_id": envelope.delivery_id,
                "envelope_core_digest": envelope.core_digest,
                "observed_at": _now_iso(),
            }
            if not duplicate_path.exists():
                _publish_json(duplicate_path, record)
            return SubmissionResult(
                "duplicate",
                envelope.handoff_id,
                envelope.delivery_id,
                str(envelope_path),
                str(payload_path),
                str(duplicate_path),
            )

        if payload_path.exists():
            if payload_path.read_bytes() != snapshot.data:
                raise HandoffError(
                    "payload_integrity_failed", "orphan payload has different bytes"
                )
        else:
            _publish_bytes(payload_path, snapshot.data)
        _publish_json(envelope_path, envelope.to_dict())
        return SubmissionResult(
            "created",
            envelope.handoff_id,
            envelope.delivery_id,
            str(envelope_path),
            str(payload_path),
        )
