from __future__ import annotations
from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from typing import Any, Literal

AgentKind = Literal["human", "ai", "system"]
Provider = Literal["mrmic", "tandem", "herdr", "ai_board", "github", "ctcl", "external"]
ResourceKind = Literal[
    "browser_tab", "browser_workspace", "browser_state_node", "terminal_agent", "terminal_pane",
    "ai_board_thread", "code_diff", "document", "image", "video", "artifact", "external_generic",
]
DisplayMode = Literal["snapshot", "live", "summary", "hidden"]
InteractionMode = Literal["inspect", "interact", "control", "read_only"]
Decision = Literal["ACK", "NO_ACTION", "ACTION", "ERROR"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

@dataclass(frozen=True)
class SemanticAgent:
    semantic_agent_id: str
    kind: AgentKind
    display_name: str
    role: str | None
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class ProviderBinding:
    binding_id: str
    semantic_agent_id: str
    provider: str
    binding_type: str
    provider_resource_id: str
    verified: bool
    native_session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class PMWWorkspace:
    pmw_workspace_id: str
    title: str
    visual_provider: str
    visual_workspace_id: str | None
    visual_canvas_id: str | None
    created_by: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class PMWTask:
    pmw_task_id: str
    pmw_workspace_id: str
    title: str
    status: str
    created_by: str
    assigned_to: list[str]
    metadata: dict[str, Any]
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class ResourceBinding:
    binding_id: str
    pmw_workspace_id: str
    provider: str
    resource_kind: str
    provider_resource_id: str
    display_mode: str
    interaction_mode: str
    owner_semantic_agent_id: str | None
    pmw_task_id: str | None
    canvas_object_id: str | None
    projection_mode: str
    state: str
    metadata: dict[str, Any]
    revision: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class PresenceEnvelope:
    semantic_agent_id: str
    pmw_workspace_id: str
    provider: str
    cursor: dict[str, float] | None
    viewport: dict[str, float] | None
    selected_object_ids: list[str]
    task: str | None
    updated_at: str
    ephemeral: bool = True

    def to_dict(self) -> dict[str, Any]: return asdict(self)

@dataclass(frozen=True)
class DecisionReceipt:
    receipt_id: str
    semantic_agent_id: str
    pmw_workspace_id: str
    pmw_task_id: str | None
    decision: str
    risk_level: str | None
    provider: str | None
    provider_resource_id: str | None
    evidence_refs: list[str]
    note: str
    created_at: str

    def to_dict(self) -> dict[str, Any]: return asdict(self)
