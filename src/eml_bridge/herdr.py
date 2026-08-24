from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Protocol, Sequence

from .errors import HerdrTransportError
from .models import AgentInfo


class HerdrAdapter(Protocol):
    def get_agent(self, target: str) -> AgentInfo: ...
    def list_agents(self) -> list[AgentInfo]: ...
    def prompt_agent(self, target: str, text: str) -> AgentInfo: ...
    def wait_agent(self, target: str, *, until: Sequence[str], timeout_ms: int) -> AgentInfo: ...
    def read_agent(self, target: str, *, lines: int = 240) -> str: ...
    def snapshot(self) -> dict: ...


class HerdrCLIAdapter:
    """Cross-platform adapter that delegates socket/protocol handling to Herdr's CLI."""

    def __init__(
        self,
        *,
        binary: str = "herdr",
        socket_path: str | None = None,
        cwd: str | Path | None = None,
        max_prompt_chars: int = 20_000,
    ):
        self.binary = binary
        self.socket_path = socket_path
        self.cwd = None if cwd is None else str(cwd)
        self.max_prompt_chars = max_prompt_chars

    def _env(self) -> dict[str, str]:
        env = os.environ.copy()
        if self.socket_path:
            env["HERDR_SOCKET_PATH"] = self.socket_path
        return env

    def _run(self, args: list[str], *, timeout_ms: int = 15_000) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.binary, *args],
                cwd=self.cwd,
                env=self._env(),
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=max(timeout_ms / 1000.0, 0.1),
                check=False,
            )
        except FileNotFoundError as exc:
            raise HerdrTransportError(f"Herdr binary not found: {self.binary}", code="binary_not_found") from exc
        except subprocess.TimeoutExpired as exc:
            raise HerdrTransportError(
                f"Herdr CLI timed out: {' '.join(args[:3])}",
                code="transport_timeout",
                ambiguous=True,
            ) from exc

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        text = text.strip()
        if not text:
            return None
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None

    def _run_json(self, args: list[str], *, timeout_ms: int = 15_000) -> dict:
        proc = self._run(args, timeout_ms=timeout_ms)
        value = self._parse_json(proc.stdout) or self._parse_json(proc.stderr)
        if proc.returncode != 0:
            code = None
            message = proc.stderr.strip() or proc.stdout.strip() or f"Herdr exited {proc.returncode}"
            if value and isinstance(value.get("error"), dict):
                code = value["error"].get("code")
                message = value["error"].get("message") or message
            raise HerdrTransportError(message, code=code, payload=value or {})
        if value is None:
            raise HerdrTransportError(
                f"Herdr command did not return JSON: {' '.join(args)}",
                code="invalid_json_response",
                payload={"stdout": proc.stdout, "stderr": proc.stderr},
            )
        if isinstance(value.get("error"), dict):
            err = value["error"]
            raise HerdrTransportError(str(err.get("message", "Herdr error")), code=err.get("code"), payload=value)
        return value

    @staticmethod
    def _agent_from_result(value: dict) -> AgentInfo:
        result = value.get("result") or {}
        agent = result.get("agent")
        if not isinstance(agent, dict):
            raise HerdrTransportError("Herdr response did not include result.agent", code="invalid_agent_response", payload=value)
        return AgentInfo.from_herdr(agent)

    def get_agent(self, target: str) -> AgentInfo:
        return self._agent_from_result(self._run_json(["agent", "get", target]))

    def list_agents(self) -> list[AgentInfo]:
        value = self._run_json(["agent", "list"])
        agents = (value.get("result") or {}).get("agents")
        if not isinstance(agents, list):
            raise HerdrTransportError("Herdr response did not include result.agents", code="invalid_agent_list", payload=value)
        return [AgentInfo.from_herdr(item) for item in agents]

    def prompt_agent(self, target: str, text: str) -> AgentInfo:
        if len(text) > self.max_prompt_chars:
            raise HerdrTransportError(
                f"Prompt is {len(text)} characters; CLI transport limit is {self.max_prompt_chars}. Use an artifact/file handoff or future direct-socket transport.",
                code="prompt_too_large",
            )
        # Deliberately no --wait. The bridge persists PROMPT_SUBMITTED after this
        # returns, then independently observes effect and settled state.
        return self._agent_from_result(self._run_json(["agent", "prompt", target, text], timeout_ms=15_000))

    def wait_agent(self, target: str, *, until: Sequence[str], timeout_ms: int) -> AgentInfo:
        args = ["agent", "wait", target]
        defaults = {"idle", "done", "blocked"}
        if set(until) != defaults:
            for status in until:
                args.extend(["--until", status])
        args.extend(["--timeout", str(int(timeout_ms))])
        return self._agent_from_result(self._run_json(args, timeout_ms=timeout_ms + 5_000))

    def read_agent(self, target: str, *, lines: int = 240) -> str:
        proc = self._run(
            ["agent", "read", target, "--source", "recent-unwrapped", "--lines", str(int(lines))],
            timeout_ms=15_000,
        )
        if proc.returncode != 0:
            value = self._parse_json(proc.stderr)
            code = None
            message = proc.stderr.strip() or f"Herdr read exited {proc.returncode}"
            if value and isinstance(value.get("error"), dict):
                code = value["error"].get("code")
                message = value["error"].get("message") or message
            raise HerdrTransportError(message, code=code, payload=value or {})
        return proc.stdout

    def snapshot(self) -> dict:
        return self._run_json(["api", "snapshot"], timeout_ms=30_000)
