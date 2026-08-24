from __future__ import annotations

import re
from dataclasses import replace
from typing import Callable, Sequence

from .errors import HerdrTransportError
from .models import AgentInfo


ResponseFn = Callable[[str, str], str]


def default_response(target: str, prompt: str) -> str:
    marker_match = re.search(r"(?m)^EML_REPLY_[A-Za-z0-9_-]+$", prompt)
    marker = marker_match.group(0) if marker_match else "EML_REPLY_MISSING"
    return f"Mock response from {target}.\n{marker}\n"


class MockHerdrAdapter:
    def __init__(self, response_fn: ResponseFn | None = None):
        self.response_fn = response_fn or default_response
        self.agents: dict[str, AgentInfo] = {}
        self.transcripts: dict[str, str] = {}
        self.pending: dict[str, tuple[str, str]] = {}
        self.prompt_calls: dict[str, int] = {}
        self.effect_disabled: set[str] = set()
        self.prompt_ambiguous: set[str] = set()

    def add_agent(self, target: str, *, kind: str, status: str = "idle", terminal_id: str | None = None) -> None:
        self.agents[target] = AgentInfo(
            terminal_id=terminal_id or f"term_{target}",
            name=target,
            agent=kind,
            agent_status=status,
            workspace_id="w1",
            tab_id="w1:t1",
            pane_id=f"w1:p{len(self.agents)+1}",
            state_change_seq=1,
            revision=1,
            agent_session={"source": "mock", "agent": kind, "kind": "session_id", "value": f"session_{target}"},
            cwd="/mock",
            interactive_ready=True,
            launch_pending=False,
        )
        self.transcripts[target] = f"[{target} ready]\n"
        self.prompt_calls[target] = 0

    def get_agent(self, target: str) -> AgentInfo:
        if target not in self.agents:
            raise HerdrTransportError(f"agent {target} not found", code="agent_not_found")
        return self.agents[target]

    def list_agents(self) -> list[AgentInfo]:
        return list(self.agents.values())

    def prompt_agent(self, target: str, text: str) -> AgentInfo:
        agent = self.get_agent(target)
        self.prompt_calls[target] += 1
        if agent.agent_status == "blocked":
            raise HerdrTransportError("agent is blocked", code="agent_blocked")
        if target in self.prompt_ambiguous:
            self.prompt_ambiguous.remove(target)
            raise HerdrTransportError("simulated disconnect after possible submission", code="transport_timeout", ambiguous=True)
        self.transcripts[target] += text
        if target in self.effect_disabled:
            return agent
        working = replace(
            agent,
            agent_status="working",
            state_change_seq=agent.state_change_seq + 1,
            revision=agent.revision + 1,
        )
        self.agents[target] = working
        self.pending[target] = (text, self.response_fn(target, text))
        return working

    def wait_agent(self, target: str, *, until: Sequence[str], timeout_ms: int) -> AgentInfo:
        agent = self.get_agent(target)
        if agent.agent_status == "blocked":
            return agent
        if target in self.pending:
            _prompt, response = self.pending.pop(target)
            self.transcripts[target] += response
            done = replace(
                agent,
                agent_status="done",
                state_change_seq=agent.state_change_seq + 1,
                revision=agent.revision + 1,
            )
            self.agents[target] = done
            return done
        if agent.agent_status in until:
            return agent
        raise HerdrTransportError("mock wait timeout", code="timeout", ambiguous=True)

    def read_agent(self, target: str, *, lines: int = 240) -> str:
        self.get_agent(target)
        return self.transcripts[target]

    def snapshot(self) -> dict:
        return {"result": {"type": "session_snapshot", "agents": [a.to_dict() for a in self.agents.values()]}}
