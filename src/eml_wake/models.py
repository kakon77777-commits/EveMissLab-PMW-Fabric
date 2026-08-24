from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .canonical import digest_ref


@dataclass(frozen=True)
class WakeRequest:
    schema_version: str
    wake_id: str
    delivery_id: str
    created_time_ref: str
    expires_at: str
    sender_claim: str
    target_kind: str
    target_ref: str
    spawn_allowed: bool
    authority_ref: str
    payload_ref: str
    payload_sha256: str
    context_package_ref: str | None
    reply_policy: str
    provider: str
    model: str
    allowed_tools: tuple[str, ...]
    permission_mode: str
    max_budget_microusd: int
    timeout_ms: int
    requested_output_format: str
    not_claimed: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WakeRequest":
        from .contracts import validate_wake_request_dict

        normalized = validate_wake_request_dict(value)
        normalized["allowed_tools"] = tuple(normalized["allowed_tools"])
        normalized["not_claimed"] = tuple(normalized["not_claimed"])
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["allowed_tools"] = list(self.allowed_tools)
        value["not_claimed"] = list(self.not_claimed)
        return value

    def core_dict(self) -> dict[str, Any]:
        value = self.to_dict()
        value.pop("delivery_id")
        return value

    @property
    def core_digest(self) -> str:
        return digest_ref(self.core_dict())


@dataclass(frozen=True)
class WakeConfig:
    schema_version: str
    allowed_payload_roots: tuple[str, ...]
    allowed_context_roots: tuple[str, ...]
    allowed_target_kinds: tuple[str, ...]
    allowed_models: tuple[str, ...]
    allowed_tools_by_policy: dict[str, tuple[str, ...]]
    permission_modes: tuple[str, ...]
    maximum_budget_microusd: int
    maximum_timeout_ms: int
    claude_binary: str
    poll_interval_ms: int
    ctcl_endpoint: str
    strict_reparse_checks: bool

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "WakeConfig":
        from .contracts import validate_wake_config_dict

        normalized = validate_wake_config_dict(value)
        normalized["allowed_payload_roots"] = tuple(normalized["allowed_payload_roots"])
        normalized["allowed_context_roots"] = tuple(normalized["allowed_context_roots"])
        normalized["allowed_target_kinds"] = tuple(normalized["allowed_target_kinds"])
        normalized["allowed_models"] = tuple(normalized["allowed_models"])
        normalized["allowed_tools_by_policy"] = {
            key: tuple(tools) for key, tools in normalized["allowed_tools_by_policy"].items()
        }
        normalized["permission_modes"] = tuple(normalized["permission_modes"])
        return cls(**normalized)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "allowed_payload_roots": list(self.allowed_payload_roots),
            "allowed_context_roots": list(self.allowed_context_roots),
            "allowed_target_kinds": list(self.allowed_target_kinds),
            "allowed_models": list(self.allowed_models),
            "allowed_tools_by_policy": {
                key: list(tools) for key, tools in self.allowed_tools_by_policy.items()
            },
            "permission_modes": list(self.permission_modes),
            "maximum_budget_microusd": self.maximum_budget_microusd,
            "maximum_timeout_ms": self.maximum_timeout_ms,
            "claude_binary": self.claude_binary,
            "poll_interval_ms": self.poll_interval_ms,
            "ctcl_endpoint": self.ctcl_endpoint,
            "strict_reparse_checks": self.strict_reparse_checks,
        }


@dataclass(frozen=True)
class ProviderResult:
    provider: str
    model: str
    provider_session_id: str
    watchdog_invocation_id: str
    result_text: str
    is_error: bool
    subtype: str | None
    stop_reason: str | None
    permission_denials: tuple[str, ...]
    cost_microusd: int
    duration_ms: int
    api_error_status: int | None


@dataclass(frozen=True)
class NotificationResult:
    notification_id: str
    attempted: bool
    accepted: bool
    route_kind: str | None = None
    ephemeral_route_ref: str | None = None
    error_code: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AckRecord:
    schema_version: str
    wake_id: str
    request_time_ref: str
    request_digest: str
    request_core_digest: str
    payload_sha256: str
    status: str
    provider: str
    model: str
    provider_session_id: str
    watchdog_invocation_id: str
    result_text: str
    provider_is_error: bool
    provider_subtype: str | None
    provider_stop_reason: str | None
    permission_denials: tuple[str, ...]
    cost_microusd: int
    duration_ms: int
    api_error_status: int | None
    temporal_evidence_status: str
    temporal_instant_id: str | None
    temporal_receipt: dict[str, Any] | None
    temporal_error_code: str | None
    weak_recorded_time: str
    reply_digest: str
    not_claimed: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["permission_denials"] = list(self.permission_denials)
        value["not_claimed"] = list(self.not_claimed)
        return value


@dataclass(frozen=True)
class FailureRecord:
    schema_version: str
    wake_id: str
    code: str
    message: str
    recorded_at: str
    details: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WatchdogResult:
    wake_id: str
    status: str
    details: dict[str, Any]
