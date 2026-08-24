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
from .identity import TargetBindingVerifier, authorize_claim
from .models import (
    ClaimRecord,
    HandoffConfig,
    HandoffEnvelope,
    MaterializationRecord,
    ReceiptRecord,
)


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

    def claim_path(self, handoff_id: str) -> Path:
        return self.claims_dir / f"{handoff_key(handoff_id)}.json"

    def materialization_path(self, handoff_id: str) -> Path:
        return self.materializations_dir / f"{handoff_key(handoff_id)}.json"

    def receipt_path(self, handoff_id: str) -> Path:
        return self.receipts_dir / f"{handoff_key(handoff_id)}.json"

    def failure_path(self, handoff_id: str) -> Path:
        return self.failures_dir / f"{handoff_key(handoff_id)}.json"

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

    def _get_claim(self, handoff_id: str) -> ClaimRecord:
        path = self.claim_path(handoff_id)
        if not path.is_file():
            raise HandoffError("handoff_not_claimed", handoff_id)
        return ClaimRecord.from_dict(_read_json(path))

    def _get_materialization(self, handoff_id: str) -> MaterializationRecord:
        path = self.materialization_path(handoff_id)
        if not path.is_file():
            raise HandoffError("payload_not_materialized", handoff_id)
        return MaterializationRecord.from_dict(_read_json(path))

    def _get_receipt(self, handoff_id: str) -> ReceiptRecord:
        path = self.receipt_path(handoff_id)
        if not path.is_file():
            raise HandoffError("receipt_not_found", handoff_id)
        return ReceiptRecord.from_dict(_read_json(path))

    def claim(
        self,
        handoff_id: str,
        *,
        receiver_instance_ref: str | None,
        binding_kind: str,
        claim_authority_ref: str,
        evidence_ref: str | None,
        receiver_entity_ref: str | None = None,
        observed_origin: str | None = None,
        verifier: TargetBindingVerifier | None = None,
    ) -> ClaimRecord:
        envelope = self.get_envelope(handoff_id)
        if self.claim_path(handoff_id).exists():
            raise HandoffError("handoff_already_claimed", handoff_id)
        authorize_claim(
            envelope,
            self.config,
            receiver_instance_ref=receiver_instance_ref,
            binding_kind=binding_kind,
            receiver_entity_ref=receiver_entity_ref,
            claim_authority_ref=claim_authority_ref,
            evidence_ref=evidence_ref,
            verifier=verifier,
        )
        record = ClaimRecord.from_dict(
            {
                "schema_version": "eml-handoff/claim-0.1",
                "handoff_id": handoff_id,
                "envelope_core_digest": envelope.core_digest,
                "receiver_instance_ref": receiver_instance_ref,
                "receiver_binding_kind": binding_kind,
                "receiver_entity_ref": receiver_entity_ref,
                "binding_evidence_ref": evidence_ref,
                "claim_authority_ref": claim_authority_ref,
                "observed_origin": observed_origin,
                "claimed_at": _now_iso(),
            }
        )
        _publish_json(self.claim_path(handoff_id), record.to_dict())
        return record

    def materialize(
        self, handoff_id: str, *, receiver_instance_ref: str | None
    ) -> MaterializationRecord:
        envelope = self.get_envelope(handoff_id)
        claim = self._get_claim(handoff_id)
        if claim.receiver_instance_ref != receiver_instance_ref:
            raise HandoffError(
                "receiver_instance_mismatch", "claim and materialization differ"
            )
        payload_path = self.payload_path(envelope)
        try:
            data = payload_path.read_bytes()
        except OSError as error:
            raise HandoffError("payload_unreadable", handoff_id) from error
        actual = sha256(data).hexdigest().upper()
        if actual != envelope.payload_sha256 or len(data) != envelope.payload_bytes:
            raise HandoffError(
                "payload_integrity_failed", "stored payload changed after commit"
            )
        record = MaterializationRecord.from_dict(
            {
                "schema_version": "eml-handoff/materialization-0.1",
                "handoff_id": handoff_id,
                "envelope_core_digest": envelope.core_digest,
                "payload_sha256": actual,
                "receiver_instance_ref": receiver_instance_ref,
                "materialized_at": _now_iso(),
                "materialization_method": "local_file_read",
            }
        )
        _publish_json(self.materialization_path(handoff_id), record.to_dict())
        return record

    def commit_receipt(
        self,
        handoff_id: str,
        *,
        decision: str,
        receiver_instance_ref: str | None,
        response_handoff_id: str | None,
        evidence_refs: list[str],
        recorded_time_ref: str | None,
    ) -> ReceiptRecord:
        envelope = self.get_envelope(handoff_id)
        materialization = self._get_materialization(handoff_id)
        if materialization.receiver_instance_ref != receiver_instance_ref:
            raise HandoffError(
                "receiver_instance_mismatch", "materialization and receipt differ"
            )
        if response_handoff_id is not None:
            try:
                response = self.get_envelope(response_handoff_id)
            except HandoffError as error:
                if error.code == "handoff_not_found":
                    raise HandoffError(
                        "response_handoff_not_found", response_handoff_id
                    ) from error
                raise
            if response.reply_to_handoff_id != handoff_id:
                raise HandoffError(
                    "response_handoff_link_mismatch", response_handoff_id
                )
        record = ReceiptRecord.from_dict(
            {
                "schema_version": "eml-handoff/receipt-0.1",
                "handoff_id": handoff_id,
                "envelope_core_digest": envelope.core_digest,
                "payload_sha256": envelope.payload_sha256,
                "receiver_instance_ref": receiver_instance_ref,
                "decision": decision,
                "response_handoff_id": response_handoff_id,
                "evidence_refs": list(evidence_refs),
                "recorded_time_ref": recorded_time_ref,
                "local_recorded_at": _now_iso(),
                "not_claimed": [
                    "payload_understood",
                    "sender_authorship_verified",
                ],
            }
        )
        _publish_json(self.receipt_path(handoff_id), record.to_dict())
        return record

    def pending(self, target_kind: str, target_ref: str) -> list[str]:
        pending: list[str] = []
        for path in sorted(self.envelopes_dir.glob("*.json")):
            envelope = HandoffEnvelope.from_dict(_read_json(path))
            if envelope.target_kind != target_kind or envelope.target_ref != target_ref:
                continue
            if self.claim_path(envelope.handoff_id).exists():
                continue
            if self.failure_path(envelope.handoff_id).exists():
                continue
            pending.append(envelope.handoff_id)
        return pending

    def status(self, handoff_id: str) -> dict[str, Any]:
        envelope = self.get_envelope(handoff_id)
        if self.receipt_path(handoff_id).is_file():
            return {
                "handoff_id": handoff_id,
                "status": "acknowledged",
                "record": self._get_receipt(handoff_id).to_dict(),
            }
        if self.materialization_path(handoff_id).is_file():
            return {
                "handoff_id": handoff_id,
                "status": "materialized",
                "record": self._get_materialization(handoff_id).to_dict(),
            }
        if self.claim_path(handoff_id).is_file():
            return {
                "handoff_id": handoff_id,
                "status": "claimed_incomplete",
                "record": self._get_claim(handoff_id).to_dict(),
            }
        if self.failure_path(handoff_id).is_file():
            return {
                "handoff_id": handoff_id,
                "status": "failed",
                "record": _read_json(self.failure_path(handoff_id)),
            }
        return {
            "handoff_id": handoff_id,
            "status": "pending",
            "record": envelope.to_dict(),
        }
