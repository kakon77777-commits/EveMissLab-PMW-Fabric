from __future__ import annotations

from datetime import datetime
from pathlib import PurePosixPath
import re
from typing import Any

from .errors import HandoffError


CTCL = re.compile(
    r"^ctcl:instant:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
HEX64 = re.compile(r"^[0-9A-F]{64}$")
DIGEST = re.compile(r"^sha256:eml-handoff-json-nfc-codepoint-v1:[0-9a-f]{64}$")

TARGET_KINDS = {"shared_topic", "task", "arcp_entity", "exact_instance"}
BINDING_KINDS = {"codex_thread", "session_uuid", "provider_session", "unresolved"}
DECISIONS = {"ACK", "NO_ACTION", "ACTION", "ERROR"}
MEDIA_BY_EXTENSION = {
    ".md": "text/markdown",
    ".json": "application/json",
    ".txt": "text/plain",
}
REQUIRED_NOT_CLAIMED = {
    "sender_authorship_verified",
    "recipient_awake",
    "recipient_identity_continuity",
    "payload_understood",
    "authority_to_act_on_payload",
    "fast_transport_delivered",
}

CONFIG_FIELDS = {
    "schema_version",
    "allowed_source_roots",
    "allowed_payload_extensions",
    "allowed_target_kinds",
    "allowed_authority_refs",
    "default_max_payload_bytes",
    "hard_max_payload_bytes",
    "ctcl_endpoint",
    "strict_reparse_checks",
}
ENVELOPE_FIELDS = {
    "schema_version",
    "handoff_id",
    "delivery_id",
    "created_time_ref",
    "temporal_evidence_status",
    "local_recorded_at",
    "claimed_sender_ref",
    "claimed_sender_instance_ref",
    "target_kind",
    "target_ref",
    "authority_ref",
    "payload_ref",
    "payload_media_type",
    "payload_sha256",
    "payload_bytes",
    "sensitivity",
    "reply_to_handoff_id",
    "expires_at",
    "not_claimed",
}
CLAIM_FIELDS = {
    "schema_version",
    "handoff_id",
    "envelope_core_digest",
    "receiver_instance_ref",
    "receiver_binding_kind",
    "receiver_entity_ref",
    "binding_evidence_ref",
    "claim_authority_ref",
    "observed_origin",
    "claimed_at",
}
MATERIALIZATION_FIELDS = {
    "schema_version",
    "handoff_id",
    "envelope_core_digest",
    "payload_sha256",
    "receiver_instance_ref",
    "materialized_at",
    "materialization_method",
}
RECEIPT_FIELDS = {
    "schema_version",
    "handoff_id",
    "envelope_core_digest",
    "payload_sha256",
    "receiver_instance_ref",
    "decision",
    "response_handoff_id",
    "evidence_refs",
    "recorded_time_ref",
    "local_recorded_at",
    "not_claimed",
}


def _shape(value: dict[str, Any], fields: set[str], schema: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HandoffError("contract_type_invalid", "record must be an object")
    unknown = sorted(set(value) - fields)
    if unknown:
        raise HandoffError("unknown_field", ",".join(unknown))
    missing = sorted(fields - set(value))
    if missing:
        raise HandoffError("missing_field", ",".join(missing))
    if value["schema_version"] != schema:
        raise HandoffError("schema_version_unsupported", str(value["schema_version"]))
    return dict(value)


def _text(value: object, field: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    if not isinstance(value, str) or not value:
        raise HandoffError("field_type_invalid", field)


def _time(value: object, field: str, *, nullable: bool = False) -> None:
    if value is None and nullable:
        return
    _text(value, field)
    assert isinstance(value, str)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise HandoffError("time_invalid", field) from error
    if parsed.tzinfo is None:
        raise HandoffError("time_invalid", field)


def _strings(value: object, field: str, *, allow_empty: bool = False) -> None:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        raise HandoffError("field_type_invalid", field)
    if not allow_empty and not value:
        raise HandoffError("field_empty", field)
    if len(value) != len(set(value)):
        raise HandoffError("duplicate_list_item", field)


def validate_config_dict(value: dict[str, Any]) -> dict[str, Any]:
    out = _shape(value, CONFIG_FIELDS, "eml-handoff/config-0.1")
    for field in (
        "allowed_source_roots",
        "allowed_payload_extensions",
        "allowed_target_kinds",
        "allowed_authority_refs",
    ):
        _strings(out[field], field)
    if not set(out["allowed_target_kinds"]) <= TARGET_KINDS:
        raise HandoffError("target_kind_unsupported", "config")
    if not set(out["allowed_payload_extensions"]) <= set(MEDIA_BY_EXTENSION):
        raise HandoffError("payload_extension_unsupported", "config")
    if any(extension != extension.lower() for extension in out["allowed_payload_extensions"]):
        raise HandoffError("payload_extension_unsupported", "extensions must be lowercase")
    default = out["default_max_payload_bytes"]
    hard = out["hard_max_payload_bytes"]
    if (
        isinstance(default, bool)
        or isinstance(hard, bool)
        or not isinstance(default, int)
        or not isinstance(hard, int)
    ):
        raise HandoffError("field_type_invalid", "payload limits")
    if not 0 < default <= hard <= 4_194_304:
        raise HandoffError("payload_limit_invalid", "config")
    _text(out["ctcl_endpoint"], "ctcl_endpoint")
    if not isinstance(out["strict_reparse_checks"], bool):
        raise HandoffError("field_type_invalid", "strict_reparse_checks")
    return out


def validate_envelope_dict(value: dict[str, Any]) -> dict[str, Any]:
    out = _shape(value, ENVELOPE_FIELDS, "eml-handoff/envelope-0.1")
    for field in (
        "handoff_id",
        "delivery_id",
        "local_recorded_at",
        "claimed_sender_ref",
        "claimed_sender_instance_ref",
        "target_ref",
        "authority_ref",
        "payload_ref",
        "payload_media_type",
    ):
        _text(out[field], field)
    _time(out["local_recorded_at"], "local_recorded_at")
    _time(out["expires_at"], "expires_at", nullable=True)
    if out["temporal_evidence_status"] == "registered_anchor":
        if not isinstance(out["created_time_ref"], str) or not CTCL.fullmatch(
            out["created_time_ref"]
        ):
            raise HandoffError(
                "temporal_evidence_mismatch", "registered anchor missing"
            )
    elif out["temporal_evidence_status"] == "unavailable":
        if out["created_time_ref"] is not None:
            raise HandoffError(
                "temporal_evidence_mismatch", "unavailable must be null"
            )
    else:
        raise HandoffError(
            "temporal_evidence_status_invalid", str(out["temporal_evidence_status"])
        )
    if out["target_kind"] not in TARGET_KINDS:
        raise HandoffError("target_kind_unsupported", str(out["target_kind"]))
    if out["sensitivity"] not in {"P0", "P1"}:
        raise HandoffError("sensitivity_not_shareable", str(out["sensitivity"]))
    if out["payload_media_type"] not in set(MEDIA_BY_EXTENSION.values()):
        raise HandoffError(
            "payload_media_type_unsupported", str(out["payload_media_type"])
        )
    if not isinstance(out["payload_sha256"], str) or not HEX64.fullmatch(
        out["payload_sha256"]
    ):
        raise HandoffError("payload_digest_invalid", "payload_sha256")
    if (
        isinstance(out["payload_bytes"], bool)
        or not isinstance(out["payload_bytes"], int)
        or out["payload_bytes"] < 0
    ):
        raise HandoffError("payload_size_invalid", "payload_bytes")
    _text(out["reply_to_handoff_id"], "reply_to_handoff_id", nullable=True)
    payload_path = PurePosixPath(out["payload_ref"])
    if (
        payload_path.is_absolute()
        or ".." in payload_path.parts
        or "\\" in out["payload_ref"]
        or not out["payload_ref"].startswith("payloads/")
    ):
        raise HandoffError("payload_ref_invalid", out["payload_ref"])
    expected_media = MEDIA_BY_EXTENSION.get(payload_path.suffix.lower())
    if expected_media != out["payload_media_type"]:
        raise HandoffError("payload_media_mismatch", out["payload_ref"])
    _strings(out["not_claimed"], "not_claimed")
    if not REQUIRED_NOT_CLAIMED <= set(out["not_claimed"]):
        raise HandoffError("not_claimed_incomplete", "envelope")
    return out


def validate_claim_dict(value: dict[str, Any]) -> dict[str, Any]:
    out = _shape(value, CLAIM_FIELDS, "eml-handoff/claim-0.1")
    for field in (
        "handoff_id",
        "envelope_core_digest",
        "receiver_binding_kind",
        "claim_authority_ref",
        "claimed_at",
    ):
        _text(out[field], field)
    if not DIGEST.fullmatch(out["envelope_core_digest"]):
        raise HandoffError("digest_invalid", "envelope_core_digest")
    if out["receiver_binding_kind"] not in BINDING_KINDS:
        raise HandoffError(
            "binding_kind_unsupported", str(out["receiver_binding_kind"])
        )
    for field in (
        "receiver_instance_ref",
        "receiver_entity_ref",
        "binding_evidence_ref",
        "observed_origin",
    ):
        _text(out[field], field, nullable=True)
    if (
        out["receiver_binding_kind"] == "unresolved"
        and out["receiver_instance_ref"] is not None
    ):
        raise HandoffError(
            "unresolved_binding_has_instance", "receiver_instance_ref"
        )
    _time(out["claimed_at"], "claimed_at")
    return out


def validate_materialization_dict(value: dict[str, Any]) -> dict[str, Any]:
    out = _shape(
        value, MATERIALIZATION_FIELDS, "eml-handoff/materialization-0.1"
    )
    for field in (
        "handoff_id",
        "envelope_core_digest",
        "payload_sha256",
        "materialized_at",
        "materialization_method",
    ):
        _text(out[field], field)
    _text(out["receiver_instance_ref"], "receiver_instance_ref", nullable=True)
    if not DIGEST.fullmatch(out["envelope_core_digest"]):
        raise HandoffError("digest_invalid", "envelope_core_digest")
    if not HEX64.fullmatch(out["payload_sha256"]):
        raise HandoffError("payload_digest_invalid", "payload_sha256")
    _time(out["materialized_at"], "materialized_at")
    if out["materialization_method"] != "local_file_read":
        raise HandoffError(
            "materialization_method_unsupported", out["materialization_method"]
        )
    return out


def validate_receipt_dict(value: dict[str, Any]) -> dict[str, Any]:
    out = _shape(value, RECEIPT_FIELDS, "eml-handoff/receipt-0.1")
    for field in (
        "handoff_id",
        "envelope_core_digest",
        "payload_sha256",
        "local_recorded_at",
    ):
        _text(out[field], field)
    _text(out["receiver_instance_ref"], "receiver_instance_ref", nullable=True)
    if not DIGEST.fullmatch(out["envelope_core_digest"]):
        raise HandoffError("digest_invalid", "envelope_core_digest")
    if not HEX64.fullmatch(out["payload_sha256"]):
        raise HandoffError("payload_digest_invalid", "payload_sha256")
    if out["decision"] not in DECISIONS:
        raise HandoffError("decision_invalid", str(out["decision"]))
    _text(out["response_handoff_id"], "response_handoff_id", nullable=True)
    _strings(out["evidence_refs"], "evidence_refs")
    _strings(out["not_claimed"], "not_claimed", allow_empty=True)
    _text(out["recorded_time_ref"], "recorded_time_ref", nullable=True)
    if out["recorded_time_ref"] is not None and not CTCL.fullmatch(
        out["recorded_time_ref"]
    ):
        raise HandoffError("ctcl_ref_invalid", "recorded_time_ref")
    _time(out["local_recorded_at"], "local_recorded_at")
    return out
