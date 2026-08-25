from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any

from eml_wake.canonical import canonical_bytes

from .errors import FederationError


RECEIPT_CANON = "pmw-receiver-adoption-json-nfc-codepoint-v1"
RECEIPT_DOMAIN = b"PMW-RECEIVER-ADOPTION\x00"
FIELDS = {
    "schema",
    "receipt_id",
    "event_id",
    "event_digest",
    "receiver_realm_id",
    "source_schema_id",
    "source_schema_sha256",
    "source_ledger_head",
    "source_view_digest",
    "decision",
    "reason_codes",
    "receiver_observation_refs",
    "authority_verification_status",
    "not_claimed",
    "receipt_digest",
}
NOT_CLAIMED = (
    "ral_head_mutated",
    "registry_commit",
    "authority_granted",
    "resident_identity_continuity",
    "source_history_rewritten",
)


@dataclass(frozen=True)
class ReceiverAdoptionReceipt:
    schema: str
    receipt_id: str
    event_id: str
    event_digest: str
    receiver_realm_id: str
    source_schema_id: str
    source_schema_sha256: str
    source_ledger_head: str
    source_view_digest: str
    decision: str
    reason_codes: tuple[str, ...]
    receiver_observation_refs: tuple[str, ...]
    authority_verification_status: str
    not_claimed: tuple[str, ...]
    receipt_digest: str

    @staticmethod
    def digest_for(value: dict[str, Any]) -> str:
        core = {key: item for key, item in value.items() if key != "receipt_digest"}
        body = (
            RECEIPT_DOMAIN
            + RECEIPT_CANON.encode("ascii")
            + b"\x00"
            + canonical_bytes(core)
        )
        return f"sha256:{RECEIPT_CANON}:" + hashlib.sha256(body).hexdigest()

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ReceiverAdoptionReceipt":
        if not isinstance(value, dict):
            raise FederationError("contract_type_invalid", "adoption receipt")
        unknown = sorted(set(value) - FIELDS)
        missing = sorted(FIELDS - set(value))
        if unknown:
            raise FederationError("unknown_field", unknown[0])
        if missing:
            raise FederationError("missing_field", missing[0])
        item = cls(
            value["schema"],
            value["receipt_id"],
            value["event_id"],
            value["event_digest"],
            value["receiver_realm_id"],
            value["source_schema_id"],
            value["source_schema_sha256"],
            value["source_ledger_head"],
            value["source_view_digest"],
            value["decision"],
            tuple(value["reason_codes"]),
            tuple(value["receiver_observation_refs"]),
            value["authority_verification_status"],
            tuple(value["not_claimed"]),
            value["receipt_digest"],
        )
        item._validate()
        return item

    def _validate(self) -> None:
        if self.schema != "pmw.receiver-adoption-receipt/v1":
            raise FederationError("schema_version_unsupported", self.schema)
        for field in (
            self.receipt_id,
            self.event_id,
            self.receiver_realm_id,
            self.source_schema_id,
        ):
            if not isinstance(field, str) or not field:
                raise FederationError("receipt_field_invalid", self.receipt_id)
        if not re.fullmatch(
            r"sha256:pmw-federated-event-json-nfc-codepoint-v1:[0-9a-f]{64}",
            self.event_digest,
        ):
            raise FederationError("event_digest_invalid", self.event_id)
        if not re.fullmatch(r"[0-9a-f]{64}", self.source_schema_sha256):
            raise FederationError("source_schema_digest_invalid", self.receipt_id)
        if not re.fullmatch(r"sha256:sedb-ral-chain-v1:[0-9a-f]{64}", self.source_ledger_head):
            raise FederationError("source_ledger_head_invalid", self.receipt_id)
        if not re.fullmatch(r"sha256:sedb-ral-json-nfc-codepoint-v1:[0-9a-f]{64}", self.source_view_digest):
            raise FederationError("source_view_digest_invalid", self.receipt_id)
        if self.decision not in {
            "adopted",
            "rejected",
            "conflict",
            "quarantined",
            "pending_dependencies",
            "unmeasured",
        }:
            raise FederationError("adoption_decision_invalid", self.decision)
        if len(self.reason_codes) != len(set(self.reason_codes)) or any(
            not isinstance(item, str) or not item for item in self.reason_codes
        ):
            raise FederationError("reason_codes_invalid", self.receipt_id)
        if not self.receiver_observation_refs or len(self.receiver_observation_refs) != len(set(self.receiver_observation_refs)):
            raise FederationError("receiver_observation_refs_invalid", self.receipt_id)
        if self.authority_verification_status not in {
            "not_required",
            "verified",
            "rejected",
            "unmeasured",
        }:
            raise FederationError(
                "authority_verification_status_invalid", self.receipt_id
            )
        if self.not_claimed != NOT_CLAIMED:
            raise FederationError("not_claimed_incomplete", self.receipt_id)
        expected = self.digest_for(self.to_dict())
        if self.receipt_digest != expected:
            raise FederationError("receipt_digest_mismatch", self.receipt_id)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["reason_codes"] = list(self.reason_codes)
        value["receiver_observation_refs"] = list(self.receiver_observation_refs)
        value["not_claimed"] = list(self.not_claimed)
        return value
