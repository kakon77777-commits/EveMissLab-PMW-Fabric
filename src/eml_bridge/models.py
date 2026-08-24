from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class DeliveryState(str, Enum):
    JOURNALED = "journaled"
    RESOLVING_TARGET = "resolving_target"
    READY = "ready"
    PROMPT_SUBMITTED = "prompt_submitted"
    ACTIVITY_OBSERVED = "activity_observed"
    RUNTIME_SETTLED = "runtime_settled"
    REPLY_CAPTURED = "reply_captured"
    ACKNOWLEDGED = "acknowledged"
    TARGET_UNAVAILABLE = "target_unavailable"
    BLOCKED = "blocked"
    SUPPRESSED = "suppressed"
    UNCERTAIN = "uncertain"
    CAPTURE_FAILED = "capture_failed"
    FAILED = "failed"
    TARGET_AUTHORITY_MISMATCH = "target_authority_mismatch"
    EXACT_NATIVE_TARGET_NOT_BOUND = "exact_native_target_not_bound"


# Runtime errata over Protocol v0.1: BLOCKED can occur after a successful prompt,
# and submission ambiguity can occur while the durable state is still READY.
ALLOWED_TRANSITIONS: dict[DeliveryState, set[DeliveryState]] = {
    DeliveryState.JOURNALED: {
        DeliveryState.RESOLVING_TARGET,
        DeliveryState.TARGET_AUTHORITY_MISMATCH,
        DeliveryState.EXACT_NATIVE_TARGET_NOT_BOUND,
        DeliveryState.FAILED,
    },
    DeliveryState.RESOLVING_TARGET: {
        DeliveryState.READY,
        DeliveryState.TARGET_UNAVAILABLE,
        DeliveryState.FAILED,
    },
    DeliveryState.READY: {
        DeliveryState.PROMPT_SUBMITTED,
        DeliveryState.BLOCKED,
        DeliveryState.UNCERTAIN,
        DeliveryState.SUPPRESSED,
        DeliveryState.FAILED,
    },
    DeliveryState.PROMPT_SUBMITTED: {
        DeliveryState.ACTIVITY_OBSERVED,
        DeliveryState.BLOCKED,
        DeliveryState.UNCERTAIN,
        DeliveryState.FAILED,
    },
    DeliveryState.ACTIVITY_OBSERVED: {
        DeliveryState.RUNTIME_SETTLED,
        DeliveryState.REPLY_CAPTURED,
        DeliveryState.BLOCKED,
        DeliveryState.UNCERTAIN,
        DeliveryState.FAILED,
    },
    DeliveryState.RUNTIME_SETTLED: {
        DeliveryState.REPLY_CAPTURED,
        DeliveryState.BLOCKED,
        DeliveryState.CAPTURE_FAILED,
        DeliveryState.UNCERTAIN,
        DeliveryState.FAILED,
    },
    DeliveryState.REPLY_CAPTURED: {
        DeliveryState.ACKNOWLEDGED,
        DeliveryState.FAILED,
    },
    DeliveryState.UNCERTAIN: {
        DeliveryState.REPLY_CAPTURED,
        DeliveryState.FAILED,
        DeliveryState.UNCERTAIN,
    },
}


class CaptureConfidence(str, Enum):
    STRUCTURED = "structured"
    TURN_FENCED = "turn_fenced"
    HEURISTIC = "heuristic"
    NONE = "none"


@dataclass(frozen=True)
class AgentInfo:
    terminal_id: str
    name: str | None
    agent: str | None
    agent_status: str
    workspace_id: str
    tab_id: str
    pane_id: str
    state_change_seq: int
    revision: int
    agent_session: dict[str, Any] | None = None
    cwd: str | None = None
    interactive_ready: bool = False
    launch_pending: bool = False

    @classmethod
    def from_herdr(cls, value: dict[str, Any]) -> "AgentInfo":
        return cls(
            terminal_id=str(value.get("terminal_id", "")),
            name=value.get("name"),
            agent=value.get("agent"),
            agent_status=str(value.get("agent_status", "unknown")),
            workspace_id=str(value.get("workspace_id", "")),
            tab_id=str(value.get("tab_id", "")),
            pane_id=str(value.get("pane_id", "")),
            state_change_seq=int(value.get("state_change_seq", 0)),
            revision=int(value.get("revision", 0)),
            agent_session=value.get("agent_session"),
            cwd=value.get("cwd"),
            interactive_ready=bool(value.get("interactive_ready", False)),
            launch_pending=bool(value.get("launch_pending", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class AgentBinding:
    semantic_agent_id: str
    display_name: str
    role: str | None
    binding_id: str
    runtime_epoch_id: str
    herdr_session: str
    agent_target: str
    agent_kind: str
    workspace_id: str
    tab_id: str
    pane_id: str
    terminal_id: str
    native_session_ref: dict[str, Any] | None
    launch_epoch: int
    bound_at: str
    status: str
    state_change_seq: int
    revision: int
    binding_confidence: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TargetLock:
    """Procedural recipient authority. Not a cryptographic or OS-level guarantee.

    Issued by a trusted controller or human workflow; a sending agent may only
    reference a lock id, never choose a recipient itself.
    """

    lock_id: str
    requested_visible_title: str
    requested_semantic_agent_id: str
    requested_native_thread_id: str | None
    issued_by: str
    issued_at: str
    allow_proxy: bool = False
    revoked_at: str | None = None
    revoked_by: str | None = None
    revocation_reason: str | None = None

    @property
    def is_revoked(self) -> bool:
        return self.revoked_at is not None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CaptureResult:
    text: str | None
    confidence: CaptureConfidence
    evidence: dict[str, Any]


@dataclass(frozen=True)
class DeliveryResult:
    message_id: str
    recipient_id: str
    state: DeliveryState
    reply_text: str | None = None
    capture_confidence: CaptureConfidence = CaptureConfidence.NONE
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "recipient_id": self.recipient_id,
            "state": self.state.value,
            "reply_text": self.reply_text,
            "capture_confidence": self.capture_confidence.value,
            "details": self.details or {},
        }
