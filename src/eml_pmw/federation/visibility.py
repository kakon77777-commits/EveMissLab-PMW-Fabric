from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import re
from typing import Any

from eml_wake.canonical import canonical_bytes

from .errors import FederationError


VISIBILITY_CANON = "pmw-adapter-visibility-json-nfc-codepoint-v1"
VISIBILITY_DOMAIN = b"PMW-ADAPTER-VISIBILITY\x00"
CTCL = re.compile(r"^ctcl:instant:[0-9a-f-]{36}$", re.IGNORECASE)
HEX64 = re.compile(r"^[0-9A-F]{64}$")
DIGEST = re.compile(
    rf"^sha256:{re.escape(VISIBILITY_CANON)}:[0-9a-f]{{64}}$"
)
FIELDS = {
    "schema",
    "evidence_id",
    "subject_task_ref",
    "subject_turn_ref",
    "adapter_kind",
    "adapter_call_count",
    "execution_state",
    "adapter_read_outcome",
    "adapter_item_count",
    "adapter_error_code",
    "local_capture_state",
    "local_capture_kind",
    "local_capture_portability",
    "materialization_state",
    "materialized_artifact_ref",
    "materialized_artifact_sha256",
    "materialized_artifact_bytes",
    "portable_delivery_state",
    "authorship_state",
    "reconciliation_state",
    "inference_barriers",
    "observed_time_ref",
    "evidence_digest",
}
INFERENCE_BARRIERS = (
    "turn_completed_does_not_imply_adapter_body_available",
    "empty_projection_does_not_imply_no_response",
    "local_capture_does_not_prove_portable_delivery",
    "materialized_handoff_does_not_prove_original_adapter_delivery",
    "delivery_or_materialization_does_not_prove_authorship_or_identity",
    "no_automatic_resend_from_empty_projection",
)


def visibility_digest(core: dict[str, Any]) -> str:
    body = (
        VISIBILITY_DOMAIN
        + VISIBILITY_CANON.encode("ascii")
        + b"\x00"
        + canonical_bytes(core)
    )
    return f"sha256:{VISIBILITY_CANON}:" + hashlib.sha256(body).hexdigest()


def _exact(value: dict[str, Any]) -> None:
    unknown = sorted(set(value) - FIELDS)
    missing = sorted(FIELDS - set(value))
    if unknown:
        raise FederationError("unknown_field", unknown[0])
    if missing:
        raise FederationError("missing_field", missing[0])


def _nonempty(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise FederationError("field_type_invalid", field)
    return value


def _nonnegative_int(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise FederationError("field_type_invalid", field)
    return value


def _relative_artifact_ref(value: str) -> bool:
    return (
        bool(value)
        and not value.startswith(("/", "\\"))
        and ":" not in value
        and "\\" not in value
        and ".." not in value.split("/")
    )


@dataclass(frozen=True)
class AdapterVisibilityEvidence:
    schema: str
    evidence_id: str
    subject_task_ref: str
    subject_turn_ref: str
    adapter_kind: str
    adapter_call_count: int
    execution_state: str
    adapter_read_outcome: str
    adapter_item_count: int
    adapter_error_code: str | None
    local_capture_state: str
    local_capture_kind: str
    local_capture_portability: str
    materialization_state: str
    materialized_artifact_ref: str | None
    materialized_artifact_sha256: str | None
    materialized_artifact_bytes: int | None
    portable_delivery_state: str
    authorship_state: str
    reconciliation_state: str
    inference_barriers: tuple[str, ...]
    observed_time_ref: str | None
    evidence_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "AdapterVisibilityEvidence":
        if not isinstance(value, dict):
            raise FederationError("contract_type_invalid", "visibility evidence")
        _exact(value)
        item = cls(
            value["schema"],
            _nonempty(value["evidence_id"], "evidence_id"),
            _nonempty(value["subject_task_ref"], "subject_task_ref"),
            _nonempty(value["subject_turn_ref"], "subject_turn_ref"),
            _nonempty(value["adapter_kind"], "adapter_kind"),
            _nonnegative_int(value["adapter_call_count"], "adapter_call_count"),
            value["execution_state"],
            value["adapter_read_outcome"],
            _nonnegative_int(value["adapter_item_count"], "adapter_item_count"),
            value["adapter_error_code"],
            value["local_capture_state"],
            value["local_capture_kind"],
            value["local_capture_portability"],
            value["materialization_state"],
            value["materialized_artifact_ref"],
            value["materialized_artifact_sha256"],
            value["materialized_artifact_bytes"],
            value["portable_delivery_state"],
            value["authorship_state"],
            value["reconciliation_state"],
            tuple(value["inference_barriers"]),
            value["observed_time_ref"],
            value["evidence_digest"],
        )
        item._validate()
        return item

    def _validate(self) -> None:
        if self.schema != "pmw.adapter-visibility-evidence/0.1":
            raise FederationError("schema_version_unsupported", self.schema)
        if self.adapter_call_count < 1:
            raise FederationError("adapter_call_count_invalid", self.evidence_id)
        if self.execution_state not in {"completed", "incomplete", "unmeasured"}:
            raise FederationError("execution_state_invalid", self.execution_state)
        if self.adapter_read_outcome not in {
            "body_available",
            "metadata_only",
            "empty_projection",
            "read_failed",
            "unmeasured",
        }:
            raise FederationError("adapter_read_outcome_invalid", self.adapter_read_outcome)
        self._validate_adapter_read()
        if self.local_capture_state not in {
            "body_observed",
            "metadata_only",
            "not_observed",
            "unmeasured",
        }:
            raise FederationError("local_capture_state_invalid", self.local_capture_state)
        if self.local_capture_kind not in {"native_transcript", "host_log", "none"}:
            raise FederationError("local_capture_kind_invalid", self.local_capture_kind)
        if self.local_capture_portability not in {
            "local_only",
            "portable_verified",
            "unmeasured",
        }:
            raise FederationError(
                "local_capture_portability_invalid", self.local_capture_portability
            )
        self._validate_local_capture()
        if self.materialization_state not in {
            "verified",
            "present_unverified",
            "absent",
            "unmeasured",
        }:
            raise FederationError(
                "materialization_state_invalid", self.materialization_state
            )
        self._validate_materialization()
        if self.portable_delivery_state not in {
            "acknowledged_structured",
            "materialized",
            "uncertain",
            "not_proven",
        }:
            raise FederationError(
                "portable_delivery_state_invalid", self.portable_delivery_state
            )
        if self.authorship_state not in {"receiver_observed", "claimed", "unmeasured"}:
            raise FederationError("authorship_state_invalid", self.authorship_state)
        if self.reconciliation_state not in {
            "locally_reconciled",
            "needs_reconciliation",
            "not_applicable",
        }:
            raise FederationError(
                "reconciliation_state_invalid", self.reconciliation_state
            )
        self._validate_inference_barriers()
        if self.observed_time_ref is not None and (
            not isinstance(self.observed_time_ref, str)
            or not CTCL.fullmatch(self.observed_time_ref)
        ):
            raise FederationError("observed_time_ref_invalid", self.evidence_id)
        if not isinstance(self.evidence_digest, str) or not DIGEST.fullmatch(
            self.evidence_digest
        ):
            raise FederationError("evidence_digest_invalid", self.evidence_id)
        expected = visibility_digest(self.core_dict())
        if self.evidence_digest != expected:
            raise FederationError("evidence_digest_mismatch", self.evidence_id)

    def _validate_adapter_read(self) -> None:
        if self.adapter_error_code is not None and (
            not isinstance(self.adapter_error_code, str) or not self.adapter_error_code
        ):
            raise FederationError("adapter_error_code_invalid", self.evidence_id)
        if self.adapter_read_outcome == "body_available":
            if self.adapter_item_count < 1 or self.adapter_error_code is not None:
                raise FederationError("adapter_read_evidence_mismatch", self.evidence_id)
        elif self.adapter_read_outcome == "read_failed":
            if self.adapter_item_count != 0 or self.adapter_error_code is None:
                raise FederationError("adapter_read_evidence_mismatch", self.evidence_id)
        elif self.adapter_read_outcome in {"empty_projection", "unmeasured"}:
            if self.adapter_item_count != 0 or self.adapter_error_code is not None:
                raise FederationError("adapter_read_evidence_mismatch", self.evidence_id)
        elif self.adapter_error_code is not None:
            raise FederationError("adapter_read_evidence_mismatch", self.evidence_id)

    def _validate_local_capture(self) -> None:
        if self.local_capture_state in {"not_observed", "unmeasured"}:
            if self.local_capture_kind != "none" or self.local_capture_portability != "unmeasured":
                raise FederationError("local_capture_evidence_mismatch", self.evidence_id)
        elif self.local_capture_kind == "none" or self.local_capture_portability == "unmeasured":
            raise FederationError("local_capture_evidence_mismatch", self.evidence_id)

    def _validate_materialization(self) -> None:
        values = (
            self.materialized_artifact_ref,
            self.materialized_artifact_sha256,
            self.materialized_artifact_bytes,
        )
        if self.materialization_state in {"verified", "present_unverified"}:
            if (
                not isinstance(values[0], str)
                or not _relative_artifact_ref(values[0])
                or not isinstance(values[1], str)
                or not HEX64.fullmatch(values[1])
                or isinstance(values[2], bool)
                or not isinstance(values[2], int)
                or values[2] < 1
            ):
                raise FederationError(
                    "materialization_evidence_incomplete", self.evidence_id
                )
        elif any(value is not None for value in values):
            raise FederationError("materialization_evidence_unexpected", self.evidence_id)

    def _validate_inference_barriers(self) -> None:
        if self.inference_barriers != INFERENCE_BARRIERS:
            raise FederationError("inference_barrier_missing", self.evidence_id)
        strong_delivery = self.portable_delivery_state in {
            "acknowledged_structured",
            "materialized",
        }
        if strong_delivery and (
            self.adapter_read_outcome == "empty_projection"
            or self.local_capture_portability == "local_only"
        ):
            raise FederationError("delivery_inference_forbidden", self.evidence_id)
        if (
            self.authorship_state == "receiver_observed"
            and self.local_capture_portability == "local_only"
        ):
            raise FederationError("authorship_inference_forbidden", self.evidence_id)

    def core_dict(self) -> dict[str, Any]:
        value = self.to_dict()
        value.pop("evidence_digest")
        return value

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["inference_barriers"] = list(self.inference_barriers)
        return value


def automatic_replay_allowed(evidence: AdapterVisibilityEvidence) -> bool:
    del evidence
    return False
