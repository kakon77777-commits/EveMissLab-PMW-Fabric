from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
from pathlib import Path

from .errors import WakeError
from .filesystem import publish_no_replace, read_canonical_file
from .models import WakeConfig, WakeRequest


def wake_key(wake_id: str) -> str:
    return hashlib.sha256(wake_id.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SubmissionResult:
    kind: str
    wake_id: str
    delivery_id: str
    request_path: str
    duplicate_path: str | None = None


class WakeStore:
    def __init__(self, root: str | Path, config: WakeConfig):
        self.root = Path(root)
        self.config = config
        self.requests_dir = self.root / "requests"
        self.claims_dir = self.root / "claims"
        self.acks_dir = self.root / "acks"
        self.failures_dir = self.root / "failures"
        self.duplicates_dir = self.root / "duplicates"
        self.notifications_dir = self.root / "notifications"
        self.quarantine_dir = self.root / "quarantine"
        for directory in (
            self.requests_dir,
            self.claims_dir,
            self.acks_dir,
            self.failures_dir,
            self.duplicates_dir,
            self.notifications_dir,
            self.quarantine_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def _path(self, directory: Path, wake_id: str) -> Path:
        return directory / f"{wake_key(wake_id)}.json"

    def request_path(self, wake_id: str) -> Path:
        return self._path(self.requests_dir, wake_id)

    def claim_path(self, wake_id: str) -> Path:
        return self._path(self.claims_dir, wake_id)

    def ack_path(self, wake_id: str) -> Path:
        return self._path(self.acks_dir, wake_id)

    def failure_path(self, wake_id: str) -> Path:
        return self._path(self.failures_dir, wake_id)

    def duplicate_path(self, wake_id: str, delivery_id: str) -> Path:
        return self.duplicates_dir / wake_key(wake_id) / f"{wake_key(delivery_id)}.json"

    def notification_path(self, wake_id: str, notification_id: str) -> Path:
        return self.notifications_dir / wake_key(wake_id) / f"{wake_key(notification_id)}.json"

    def submit(self, request: WakeRequest) -> SubmissionResult:
        path = self.request_path(request.wake_id)
        if not path.exists():
            publish_no_replace(path, request.to_dict())
            return SubmissionResult("created", request.wake_id, request.delivery_id, str(path))

        existing = self.get_request(request.wake_id)
        if existing.core_digest != request.core_digest:
            raise WakeError(
                "wake_content_collision",
                "same wake_id was submitted with different core content",
                details={"existing": existing.core_digest, "submitted": request.core_digest},
            )
        duplicate = self.duplicate_path(request.wake_id, request.delivery_id)
        record = {
            "schema_version": "eml-wake/duplicate-0.1",
            "wake_id": request.wake_id,
            "delivery_id": request.delivery_id,
            "request_core_digest": request.core_digest,
            "observed_at": _now_iso(),
        }
        if duplicate.exists():
            if read_canonical_file(duplicate) != record:
                existing_record = read_canonical_file(duplicate)
                if existing_record.get("request_core_digest") != request.core_digest:
                    raise WakeError("duplicate_content_collision", "duplicate delivery record conflicts")
            return SubmissionResult("duplicate", request.wake_id, request.delivery_id, str(path), str(duplicate))
        publish_no_replace(duplicate, record)
        return SubmissionResult("duplicate", request.wake_id, request.delivery_id, str(path), str(duplicate))

    def get_request(self, wake_id: str) -> WakeRequest:
        path = self.request_path(wake_id)
        if not path.is_file():
            raise WakeError("wake_not_found", f"wake request not found: {wake_id}")
        request = WakeRequest.from_dict(read_canonical_file(path))
        if request.wake_id != wake_id:
            raise WakeError("wake_filename_mismatch", "request content does not match requested wake id")
        return request

    def claim(self, wake_id: str, watchdog_id: str) -> dict:
        request = self.get_request(wake_id)
        record = {
            "schema_version": "eml-wake/claim-0.1",
            "wake_id": wake_id,
            "watchdog_id": watchdog_id,
            "request_core_digest": request.core_digest,
            "claimed_at": _now_iso(),
        }
        try:
            publish_no_replace(self.claim_path(wake_id), record)
        except WakeError as exc:
            if exc.code == "immutable_file_exists":
                raise WakeError("wake_already_claimed", f"wake is already claimed: {wake_id}") from exc
            raise
        return record

    def commit_ack(self, wake_id: str, ack: dict) -> Path:
        if ack.get("wake_id") != wake_id:
            raise WakeError("ack_wake_mismatch", "ACK wake_id does not match target wake")
        if not self.claim_path(wake_id).is_file():
            raise WakeError("wake_not_claimed", "ACK cannot be committed before claim")
        path = self.ack_path(wake_id)
        publish_no_replace(path, ack)
        return path

    def record_failure(self, wake_id: str, failure: dict) -> Path:
        if failure.get("wake_id") != wake_id:
            raise WakeError("failure_wake_mismatch", "failure wake_id does not match target wake")
        self.get_request(wake_id)
        path = self.failure_path(wake_id)
        publish_no_replace(path, failure)
        return path

    def record_notification(self, wake_id: str, notification: dict) -> Path:
        if notification.get("wake_id") != wake_id:
            raise WakeError("notification_wake_mismatch", "notification wake_id does not match target wake")
        notification_id = notification.get("notification_id")
        if not isinstance(notification_id, str) or not notification_id:
            raise WakeError("notification_id_missing", "notification_id is required")
        self.get_request(wake_id)
        path = self.notification_path(wake_id, notification_id)
        publish_no_replace(path, notification)
        return path

    def status(self, wake_id: str) -> dict:
        request = self.get_request(wake_id)
        if self.ack_path(wake_id).is_file():
            return {"wake_id": wake_id, "status": "acknowledged", "record": read_canonical_file(self.ack_path(wake_id))}
        if self.failure_path(wake_id).is_file():
            return {"wake_id": wake_id, "status": "failed", "record": read_canonical_file(self.failure_path(wake_id))}
        if self.claim_path(wake_id).is_file():
            return {
                "wake_id": wake_id,
                "status": "claimed_incomplete",
                "record": read_canonical_file(self.claim_path(wake_id)),
            }
        return {"wake_id": wake_id, "status": "pending", "record": request.to_dict()}

    def pending_wake_ids(self) -> list[str]:
        pending: list[str] = []
        for path in sorted(self.requests_dir.glob("*.json")):
            request = WakeRequest.from_dict(read_canonical_file(path))
            if not self.claim_path(request.wake_id).exists() and not self.failure_path(request.wake_id).exists():
                pending.append(request.wake_id)
        return pending
