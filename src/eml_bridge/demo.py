from __future__ import annotations

import json
from pathlib import Path
import re

from .core import BridgeEngine
from .journal import SQLiteJournal
from .message import new_message, reply_message
from .mock_herdr import MockHerdrAdapter
from .sinks import JsonlBoardSink, JsonlProvenanceSink


def _response(target: str, prompt: str) -> str:
    marker_match = re.search(r"(?m)^EML_REPLY_[A-Za-z0-9_-]+$", prompt)
    marker = marker_match.group(0) if marker_match else "EML_REPLY_MISSING"
    if target == "codex-reviewer":
        body = (
            "Codex reviewer: the delegated check is complete. The quantifier order must be stated "
            "before selecting the witness; otherwise the claimed uniform witness is not justified."
        )
    else:
        body = "Claude main: received the Codex finding and recorded it for the parent research thread."
    return f"{body}\n{marker}\n"


def run_demo(root: Path) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    db = root / "bridge.sqlite3"
    for artifact in (db, root / "ai_board_dev.jsonl", root / "provenance_dev.jsonl", root / "demo_result.json"):
        if artifact.exists():
            artifact.unlink()
    for suffix in ("-wal", "-shm"):
        side = Path(str(db) + suffix)
        if side.exists():
            side.unlink()
    mock = MockHerdrAdapter(_response)
    mock.add_agent("claude-main", kind="claude")
    mock.add_agent("codex-reviewer", kind="codex")
    journal = SQLiteJournal(db)
    try:
        engine = BridgeEngine(
            journal=journal,
            herdr=mock,
            board_sink=JsonlBoardSink(root / "ai_board_dev.jsonl"),
            provenance_sink=JsonlProvenanceSink(root / "provenance_dev.jsonl"),
            prompt_effect_timeout_ms=100,
            poll_interval_ms=1,
        )
        engine.bind_agent(
            "agent://evemisslab/research/claude-main",
            "claude-main",
            display_name="Claude Main",
            role="primary researcher",
        )
        engine.bind_agent(
            "agent://evemisslab/research/codex-reviewer",
            "codex-reviewer",
            display_name="Codex Reviewer",
            role="independent reviewer",
        )
        lock = journal.create_target_lock(
            requested_visible_title="Codex Reviewer",
            requested_semantic_agent_id="agent://evemisslab/research/codex-reviewer",
            issued_by="demo-controller",
        )
        request = new_message(
            sender="agent://evemisslab/research/claude-main",
            recipient="agent://evemisslab/research/codex-reviewer",
            target_lock=lock,
            text="Review Lemma 3. Focus on quantifier order.",
            route_intent="delegate",
            projection="board_and_prompt",
        )
        first = engine.deliver(request)
        followup = reply_message(
            request,
            sender="agent://evemisslab/research/codex-reviewer",
            text=first.reply_text or "No captured response",
        )
        second = engine.deliver(followup)
        output = {
            "request": request,
            "codex_delivery": first.to_dict(),
            "return_message": followup,
            "claude_delivery": second.to_dict(),
            "thread": journal.list_thread(request["thread_id"]),
            "prompt_calls": mock.prompt_calls,
            "artifacts": {
                "db": str(db),
                "board": str(root / "ai_board_dev.jsonl"),
                "provenance": str(root / "provenance_dev.jsonl"),
            },
        }
        (root / "demo_result.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
        return output
    finally:
        journal.close()
