from __future__ import annotations

from datetime import datetime
import re
from typing import Any

from .errors import WakeError


_CTCL_RE = re.compile(
    r"^ctcl:instant:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$", re.IGNORECASE)
_REQUEST_FIELDS = {
    "schema_version",
    "wake_id",
    "delivery_id",
    "created_time_ref",
    "expires_at",
    "sender_claim",
    "target_kind",
    "target_ref",
    "spawn_allowed",
    "authority_ref",
    "payload_ref",
    "payload_sha256",
    "context_package_ref",
    "reply_policy",
    "provider",
    "model",
    "allowed_tools",
    "permission_mode",
    "max_budget_microusd",
    "timeout_ms",
    "requested_output_format",
    "not_claimed",
}
_CONFIG_FIELDS = {
    "schema_version",
    "allowed_payload_roots",
    "allowed_context_roots",
    "allowed_target_kinds",
    "allowed_models",
    "allowed_tools_by_policy",
    "permission_modes",
    "maximum_budget_microusd",
    "maximum_timeout_ms",
    "claude_binary",
    "poll_interval_ms",
    "ctcl_endpoint",
    "strict_reparse_checks",
}


def _exact_fields(value: dict[str, Any], expected: set[str]) -> None:
    unknown = sorted(set(value) - expected)
    if unknown:
        raise WakeError("unknown_field", f"unknown field: {unknown[0]}", details={"fields": unknown})
    missing = sorted(expected - set(value))
    if missing:
        raise WakeError("missing_field", f"missing field: {missing[0]}", details={"fields": missing})


def _string(value: Any, field: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        raise WakeError("field_type_invalid", f"{field} must be a non-empty string")
    return value


def _integer(value: Any, field: str, *, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise WakeError("field_type_invalid", f"{field} must be an integer")
    if value < minimum:
        raise WakeError("field_value_invalid", f"{field} must be at least {minimum}")
    return value


def _string_list(value: Any, field: str, *, allow_empty: bool = True) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        raise WakeError("field_type_invalid", f"{field} must be a list of non-empty strings")
    if not allow_empty and not value:
        raise WakeError("config_allowlist_empty", f"{field} must not be empty")
    if len(set(value)) != len(value):
        raise WakeError("field_value_invalid", f"{field} contains duplicate values")
    return list(value)


def _utc_time(value: Any, field: str) -> str:
    text = _string(value, field)
    if not text.endswith("Z"):
        raise WakeError("utc_time_required", f"{field} must use a UTC Z suffix")
    try:
        datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise WakeError("utc_time_invalid", f"{field} is not a valid RFC3339 UTC time") from exc
    return text


def validate_wake_request_dict(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WakeError("contract_type_invalid", "wake request must be an object")
    _exact_fields(value, _REQUEST_FIELDS)
    result = dict(value)
    if value["schema_version"] != "eml-wake/request-0.1":
        raise WakeError("schema_version_unsupported", "unsupported wake request schema")
    for field in ("wake_id", "delivery_id", "sender_claim", "target_ref", "authority_ref", "payload_ref", "model"):
        result[field] = _string(value[field], field)
    if not _CTCL_RE.fullmatch(_string(value["created_time_ref"], "created_time_ref")):
        raise WakeError("ctcl_ref_invalid", "created_time_ref must be a registered CTCL instant id")
    result["expires_at"] = _utc_time(value["expires_at"], "expires_at")
    target_kind = _string(value["target_kind"], "target_kind")
    if target_kind not in {"exact_instance", "line", "generic_worker"}:
        raise WakeError("target_kind_unsupported", f"unsupported target_kind: {target_kind}")
    result["target_kind"] = target_kind
    if not isinstance(value["spawn_allowed"], bool):
        raise WakeError("field_type_invalid", "spawn_allowed must be boolean")
    if target_kind == "exact_instance" and value["spawn_allowed"]:
        raise WakeError("exact_instance_spawn_forbidden", "exact-instance requests cannot authorize spawn")
    if target_kind in {"line", "generic_worker"} and not value["spawn_allowed"]:
        raise WakeError("spawn_authority_missing", "spawn target requires spawn_allowed=true")
    sha = _string(value["payload_sha256"], "payload_sha256")
    if not _HEX64_RE.fullmatch(sha):
        raise WakeError("payload_digest_invalid", "payload_sha256 must be 64 hexadecimal characters")
    result["payload_sha256"] = sha.upper()
    context = value["context_package_ref"]
    if context is not None and (not isinstance(context, str) or not context):
        raise WakeError("field_type_invalid", "context_package_ref must be null or a non-empty string")
    if target_kind == "line" and context is None:
        raise WakeError("line_context_missing", "line target requires context_package_ref")
    if value["reply_policy"] != "durable_ack_only":
        raise WakeError("reply_policy_unsupported", "only durable_ack_only is supported")
    if value["provider"] != "claude":
        raise WakeError("provider_unsupported", "only the claude provider is supported")
    result["allowed_tools"] = _string_list(value["allowed_tools"], "allowed_tools")
    if value["permission_mode"] != "dontAsk":
        raise WakeError("permission_mode_unsupported", "only dontAsk is supported in Version 1")
    result["max_budget_microusd"] = _integer(value["max_budget_microusd"], "max_budget_microusd")
    result["timeout_ms"] = _integer(value["timeout_ms"], "timeout_ms")
    if value["requested_output_format"] != "json":
        raise WakeError("output_format_unsupported", "only JSON provider output is supported")
    result["not_claimed"] = _string_list(value["not_claimed"], "not_claimed")
    return result


def validate_wake_config_dict(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise WakeError("contract_type_invalid", "wake config must be an object")
    _exact_fields(value, _CONFIG_FIELDS)
    if value["schema_version"] != "eml-wake/config-0.1":
        raise WakeError("schema_version_unsupported", "unsupported wake config schema")
    result = dict(value)
    result["allowed_payload_roots"] = _string_list(
        value["allowed_payload_roots"], "allowed_payload_roots", allow_empty=False
    )
    result["allowed_context_roots"] = _string_list(value["allowed_context_roots"], "allowed_context_roots")
    result["allowed_target_kinds"] = _string_list(
        value["allowed_target_kinds"], "allowed_target_kinds", allow_empty=False
    )
    if not set(result["allowed_target_kinds"]).issubset({"line", "generic_worker"}):
        raise WakeError("target_kind_unsupported", "config may allow only line and generic_worker")
    result["allowed_models"] = _string_list(value["allowed_models"], "allowed_models", allow_empty=False)
    policies = value["allowed_tools_by_policy"]
    if not isinstance(policies, dict) or not policies:
        raise WakeError("config_allowlist_empty", "allowed_tools_by_policy must not be empty")
    normalized_policies: dict[str, list[str]] = {}
    for key, tools in policies.items():
        name = _string(key, "allowed_tools_by_policy key")
        normalized_policies[name] = _string_list(tools, f"allowed_tools_by_policy.{name}")
    result["allowed_tools_by_policy"] = normalized_policies
    result["permission_modes"] = _string_list(value["permission_modes"], "permission_modes", allow_empty=False)
    result["maximum_budget_microusd"] = _integer(
        value["maximum_budget_microusd"], "maximum_budget_microusd"
    )
    result["maximum_timeout_ms"] = _integer(value["maximum_timeout_ms"], "maximum_timeout_ms")
    result["claude_binary"] = _string(value["claude_binary"], "claude_binary")
    result["poll_interval_ms"] = _integer(value["poll_interval_ms"], "poll_interval_ms")
    endpoint = _string(value["ctcl_endpoint"], "ctcl_endpoint")
    if not endpoint.startswith("https://"):
        raise WakeError("ctcl_endpoint_invalid", "ctcl_endpoint must use HTTPS")
    if not isinstance(value["strict_reparse_checks"], bool):
        raise WakeError("field_type_invalid", "strict_reparse_checks must be boolean")
    return result
