from __future__ import annotations

from dataclasses import replace
import tempfile
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_bridge.capture import capture_reply
from eml_bridge.core import BridgeEngine
from eml_bridge.errors import HerdrTransportError
from eml_bridge.journal import SQLiteJournal
from eml_bridge.message import new_message
from eml_bridge.mock_herdr import MockHerdrAdapter
from eml_bridge.models import CaptureConfidence, DeliveryState


def response(target: str, prompt: str) -> str:
    marker = re.search(r"(?m)^EML_REPLY_[A-Za-z0-9_-]+$", prompt).group(0)
    return f"answer from {target}\n{marker}\n"


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "bridge.sqlite3"
        self.journal = SQLiteJournal(self.db)
        self.mock = MockHerdrAdapter(response)
        self.mock.add_agent("claude-main", kind="claude")
        self.mock.add_agent("codex-reviewer", kind="codex")
        self.engine = BridgeEngine(
            journal=self.journal,
            herdr=self.mock,
            prompt_effect_timeout_ms=20,
            poll_interval_ms=1,
        )
        self.claude = "agent://evemisslab/research/claude-main"
        self.codex = "agent://evemisslab/research/codex-reviewer"
        self.engine.bind_agent(self.claude, "claude-main")
        self.engine.bind_agent(self.codex, "codex-reviewer")
        # Proactive sends now need issued recipient authority; the assertions below
        # are unchanged, they simply run through the preflight gate.
        self.lock = self.journal.create_target_lock(
            requested_visible_title="Codex Reviewer",
            requested_semantic_agent_id=self.codex,
            issued_by="test-controller",
        )

    def tearDown(self):
        self.journal.close()
        self.tmp.cleanup()

    def msg(self, **overrides):
        args = dict(
            sender=self.claude,
            recipient=self.codex,
            text="check lemma",
            route_intent="delegate",
            target_lock=self.lock,
        )
        args.update(overrides)
        return new_message(**args)

    def test_successful_turn_fenced_delivery(self):
        result = self.engine.deliver(self.msg())
        self.assertEqual(result.state, DeliveryState.ACKNOWLEDGED)
        self.assertEqual(result.capture_confidence, CaptureConfidence.TURN_FENCED)
        self.assertIn("answer from codex-reviewer", result.reply_text)
        self.assertEqual(self.mock.prompt_calls["codex-reviewer"], 1)

    def test_prompt_effect_not_observed_is_uncertain_and_not_replayed(self):
        self.mock.effect_disabled.add("codex-reviewer")
        message = self.msg()
        first = self.engine.deliver(message)
        second = self.engine.deliver(message)
        self.assertEqual(first.state, DeliveryState.UNCERTAIN)
        self.assertEqual(second.state, DeliveryState.UNCERTAIN)
        self.assertEqual(self.mock.prompt_calls["codex-reviewer"], 1)

    def test_ambiguous_submit_is_uncertain(self):
        self.mock.prompt_ambiguous.add("codex-reviewer")
        result = self.engine.deliver(self.msg())
        self.assertEqual(result.state, DeliveryState.UNCERTAIN)
        self.assertEqual(result.details["reason"], "submission_ambiguous")

    def test_blocked_target_is_not_prompted(self):
        self.mock.agents["codex-reviewer"] = replace(self.mock.agents["codex-reviewer"], agent_status="blocked")
        result = self.engine.deliver(self.msg())
        self.assertEqual(result.state, DeliveryState.BLOCKED)
        self.assertEqual(self.mock.prompt_calls["codex-reviewer"], 0)

    def test_unknown_target_is_deferred_without_send(self):
        self.mock.agents["codex-reviewer"] = replace(self.mock.agents["codex-reviewer"], agent_status="unknown")
        result = self.engine.deliver(self.msg())
        self.assertEqual(result.state, DeliveryState.TARGET_UNAVAILABLE)
        self.assertEqual(result.details["reason"], "target_status_unknown_strict_turn")
        self.assertEqual(self.mock.prompt_calls["codex-reviewer"], 0)

    def test_duplicate_payload_route_is_suppressed(self):
        first = self.msg()
        result1 = self.engine.deliver(first)
        self.assertEqual(result1.state, DeliveryState.ACKNOWLEDGED)
        second = self.msg(thread_id=first["thread_id"])
        result2 = self.engine.deliver(second)
        self.assertEqual(result2.state, DeliveryState.SUPPRESSED)
        self.assertEqual(result2.details["reason"], "duplicate_payload_route")
        self.assertEqual(self.mock.prompt_calls["codex-reviewer"], 1)

    def test_stale_binding_refuses_new_occupant(self):
        old = self.mock.agents["codex-reviewer"]
        self.mock.agents["codex-reviewer"] = replace(
            old,
            terminal_id="term_replaced",
            agent_session={"source": "mock", "agent": "codex", "kind": "session_id", "value": "different"},
        )
        result = self.engine.deliver(self.msg())
        self.assertEqual(result.state, DeliveryState.TARGET_UNAVAILABLE)
        self.assertEqual(self.mock.prompt_calls["codex-reviewer"], 0)

    def test_native_session_allows_coordinate_rebind(self):
        old = self.mock.agents["codex-reviewer"]
        self.mock.agents["codex-reviewer"] = replace(
            old,
            terminal_id="term_new",
            pane_id="w2:p9",
            workspace_id="w2",
            tab_id="w2:t1",
        )
        binding = self.engine.reconcile_agent(self.codex)
        self.assertEqual(binding["terminal_id"], "term_new")
        self.assertEqual(binding["pane_id"], "w2:p9")

    def test_structured_reply_has_highest_confidence(self):
        message = self.msg()
        self.journal.record_structured_reply(message["message_id"], self.codex, "structured result")
        result = self.engine.deliver(message)
        self.assertEqual(result.state, DeliveryState.ACKNOWLEDGED)
        self.assertEqual(result.capture_confidence, CaptureConfidence.STRUCTURED)
        self.assertEqual(result.reply_text, "structured result")

    def test_board_only_has_no_prompt_side_effect(self):
        result = self.engine.deliver(self.msg(projection="board_only"))
        self.assertEqual(result.state, DeliveryState.SUPPRESSED)
        self.assertEqual(self.mock.prompt_calls["codex-reviewer"], 0)


class CaptureTests(unittest.TestCase):
    def test_prompt_echo_marker_is_not_sufficient_without_response_tail(self):
        marker = "EML_REPLY_msg_x_abcdef123456"
        before = "ready\n"
        frame = f"BEGIN_MESSAGE\nhello\nEND_MESSAGE\nappend:\n{marker}\n[/EML-BRIDGE]\n"
        result = capture_reply(before, before + frame, marker)
        self.assertNotEqual(result.confidence, CaptureConfidence.TURN_FENCED)

    def test_marker_after_bridge_frame_is_turn_fenced(self):
        marker = "EML_REPLY_msg_x_abcdef123456"
        before = "ready\n"
        frame = f"BEGIN_MESSAGE\nhello\nEND_MESSAGE\nappend:\n{marker}\n[/EML-BRIDGE]\n"
        after = before + frame + "actual answer\n" + marker + "\n"
        result = capture_reply(before, after, marker)
        self.assertEqual(result.confidence, CaptureConfidence.TURN_FENCED)
        self.assertEqual(result.text, "actual answer")


class BlockedAfterPromptMock(MockHerdrAdapter):
    def wait_agent(self, target: str, *, until, timeout_ms: int):
        agent = self.get_agent(target)
        blocked = replace(agent, agent_status="blocked", state_change_seq=agent.state_change_seq + 1)
        self.agents[target] = blocked
        return blocked


class StructuredReplyThenTimeoutMock(MockHerdrAdapter):
    def __init__(self, journal: SQLiteJournal, recipient: str):
        super().__init__(response)
        self.journal = journal
        self.recipient = recipient
        self.parent_message_id: str | None = None

    def prompt_agent(self, target: str, text: str):
        match = re.search(r"(?m)^message_id: (msg_[A-Za-z0-9_-]+)$", text)
        if match is None:
            raise AssertionError("bridge frame did not contain a message_id")
        self.parent_message_id = match.group(1)
        return super().prompt_agent(target, text)

    def wait_agent(self, target: str, *, until, timeout_ms: int):
        if self.parent_message_id is None:
            raise AssertionError("prompt_agent was not called before wait_agent")
        self.journal.record_structured_reply(
            self.parent_message_id,
            self.recipient,
            "structured result before runtime settlement",
        )
        raise HerdrTransportError("mock wait timeout", code="timeout", ambiguous=True)


class ErratumTests(unittest.TestCase):
    def test_blocked_is_reachable_after_prompt_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = SQLiteJournal(Path(tmp) / "b.sqlite3")
            mock = BlockedAfterPromptMock(response)
            mock.add_agent("codex-reviewer", kind="codex")
            engine = BridgeEngine(journal=journal, herdr=mock, prompt_effect_timeout_ms=20, poll_interval_ms=1)
            recipient = "agent://evemisslab/research/codex-reviewer"
            engine.bind_agent(recipient, "codex-reviewer")
            lock = journal.create_target_lock(
                requested_visible_title="Codex Reviewer",
                requested_semantic_agent_id=recipient,
                issued_by="test-controller",
            )
            msg = new_message(
                sender="agent://evemisslab/research/claude-main",
                recipient=recipient,
                text="work",
                target_lock=lock,
            )
            result = engine.deliver(msg)
            self.assertEqual(result.state, DeliveryState.BLOCKED)
            states = [x["state"] for x in journal.get_delivery(msg["message_id"], recipient)["history"]]
            self.assertIn("activity_observed", states)
            journal.close()

    def test_structured_reply_survives_runtime_settlement_timeout(self):
        with tempfile.TemporaryDirectory() as tmp:
            journal = SQLiteJournal(Path(tmp) / "structured-timeout.sqlite3")
            try:
                recipient = "agent://evemisslab/research/codex-reviewer"
                mock = StructuredReplyThenTimeoutMock(journal, recipient)
                mock.add_agent("codex-reviewer", kind="codex")
                engine = BridgeEngine(journal=journal, herdr=mock, prompt_effect_timeout_ms=20, poll_interval_ms=1)
                engine.bind_agent(recipient, "codex-reviewer")
                lock = journal.create_target_lock(
                    requested_visible_title="Codex Reviewer",
                    requested_semantic_agent_id=recipient,
                    issued_by="test-controller",
                )
                message = new_message(
                    sender="agent://evemisslab/research/claude-main",
                    recipient=recipient,
                    text="work",
                    target_lock=lock,
                )

                result = engine.deliver(message)

                self.assertEqual(result.state, DeliveryState.ACKNOWLEDGED)
                self.assertEqual(result.capture_confidence, CaptureConfidence.STRUCTURED)
                self.assertEqual(result.reply_text, "structured result before runtime settlement")
                self.assertFalse(result.details["capture_evidence"]["runtime_settled"])
                states = [
                    item["state"]
                    for item in journal.get_delivery(message["message_id"], recipient)["history"]
                ]
                self.assertNotIn(DeliveryState.RUNTIME_SETTLED.value, states)

                replay_guard = engine.deliver(message)
                self.assertEqual(replay_guard.state, DeliveryState.ACKNOWLEDGED)
                self.assertEqual(replay_guard.reply_text, "structured result before runtime settlement")
                self.assertEqual(mock.prompt_calls["codex-reviewer"], 1)
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
