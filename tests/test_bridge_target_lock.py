from __future__ import annotations

import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_bridge.core import BridgeEngine
from eml_bridge.journal import SQLiteJournal
from eml_bridge.message import new_message, reply_message
from eml_bridge.mock_herdr import MockHerdrAdapter
from eml_bridge.models import DeliveryState


ZHIYU = "agent://evemisslab/line/zhiyu"
CODEX_PEER = "agent://evemisslab/pane/codex-peer"
CLAUDE_MAIN = "agent://evemisslab/research/claude-main"
ZHIYU_TITLE = "織域-cross-provider integration steward"
ZHIYU_THREAD = "019fe51e-9276-7f63-8c16-414624b7fa9d"


def response(target: str, prompt: str) -> str:
    marker = re.search(r"(?m)^EML_REPLY_[A-Za-z0-9_-]+$", prompt).group(0)
    return f"answer from {target}\n{marker}\n"


class TargetLockTests(unittest.TestCase):
    """Recipient authority belongs to the lock, never to the sending agent.

    Every refusal here must leave the Herdr prompt count at 0: a refused send is
    not a send that failed late, it is a send that never touched the runtime.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = SQLiteJournal(Path(self.tmp.name) / "bridge.sqlite3")
        self.mock = MockHerdrAdapter(response)
        self.mock.add_agent("codex-peer", kind="codex")
        self.engine = BridgeEngine(
            journal=self.journal,
            herdr=self.mock,
            prompt_effect_timeout_ms=20,
            poll_interval_ms=1,
        )
        self.engine.bind_agent(CODEX_PEER, "codex-peer")

    def tearDown(self):
        self.journal.close()
        self.tmp.cleanup()

    def zhiyu_lock(self, *, allow_proxy: bool = False):
        return self.journal.create_target_lock(
            requested_visible_title=ZHIYU_TITLE,
            requested_semantic_agent_id=ZHIYU,
            requested_native_thread_id=ZHIYU_THREAD,
            issued_by="human:neo",
            allow_proxy=allow_proxy,
        )

    def prompts(self) -> int:
        return sum(self.mock.prompt_calls.values())

    # 1
    def test_lock_names_zhiyu_but_send_addresses_codex_peer_is_refused(self):
        lock = self.zhiyu_lock()
        message = new_message(
            sender=CLAUDE_MAIN, recipient=CODEX_PEER, text="hello", target_lock=lock
        )
        result = self.engine.deliver(message)
        self.assertEqual(result.state, DeliveryState.TARGET_AUTHORITY_MISMATCH)
        self.assertEqual(result.details["reason"], "actual_recipient_not_equal_to_lock")
        self.assertEqual(self.prompts(), 0)

    # 2
    def test_exact_native_target_not_bound_when_zhiyu_has_no_binding(self):
        lock = self.zhiyu_lock()
        message = new_message(
            sender=CLAUDE_MAIN, recipient=ZHIYU, text="hello", target_lock=lock
        )
        result = self.engine.deliver(message)
        self.assertEqual(result.state, DeliveryState.EXACT_NATIVE_TARGET_NOT_BOUND)
        self.assertEqual(result.details["reason"], "semantic_agent_not_bound")
        self.assertEqual(self.prompts(), 0)

    # 3
    def test_allow_proxy_false_never_resolves_to_a_proxy_runtime(self):
        # zhiyu is bound, but to a runtime whose native session is not the locked thread
        self.engine.bind_agent(ZHIYU, "codex-peer")
        lock = self.zhiyu_lock(allow_proxy=False)
        message = new_message(
            sender=CLAUDE_MAIN, recipient=ZHIYU, text="hello", target_lock=lock
        )
        result = self.engine.deliver(message)
        self.assertEqual(result.state, DeliveryState.EXACT_NATIVE_TARGET_NOT_BOUND)
        self.assertEqual(result.details["reason"], "native_thread_ref_mismatch")
        self.assertEqual(self.prompts(), 0)

    # 4
    def test_proactive_direct_send_without_a_lock_fails_closed(self):
        message = new_message(sender=CLAUDE_MAIN, recipient=CODEX_PEER, text="hello")
        result = self.engine.deliver(message)
        self.assertEqual(result.state, DeliveryState.TARGET_AUTHORITY_MISMATCH)
        self.assertEqual(result.details["reason"], "target_lock_required")
        self.assertEqual(self.prompts(), 0)

    # 5
    def test_parent_derived_structured_reply_still_needs_no_lock(self):
        inbound = new_message(
            sender=CODEX_PEER,
            recipient=CLAUDE_MAIN,
            text="question",
            target_lock=self.journal.create_target_lock(
                requested_visible_title="Claude Main",
                requested_semantic_agent_id=CLAUDE_MAIN,
                issued_by="human:neo",
            ),
        )
        self.journal.journal_message(inbound)
        outbound = reply_message(inbound, sender=CLAUDE_MAIN, text="answer")
        self.assertEqual(outbound["target_authority"]["mode"], "parent_derived")
        self.assertEqual(outbound["recipients"][0]["semantic_agent_id"], CODEX_PEER)

        result = self.engine.deliver(outbound)
        self.assertNotIn(
            result.state,
            {
                DeliveryState.TARGET_AUTHORITY_MISMATCH,
                DeliveryState.EXACT_NATIVE_TARGET_NOT_BOUND,
            },
        )

    # 6
    def test_audit_evidence_keeps_requested_resolved_and_actual(self):
        self.engine.bind_agent(ZHIYU, "codex-peer")
        lock = self.zhiyu_lock(allow_proxy=True)
        message = new_message(
            sender=CLAUDE_MAIN, recipient=ZHIYU, text="hello", target_lock=lock
        )
        self.engine.deliver(message)
        delivery = self.journal.get_delivery(message["message_id"], ZHIYU)
        evidence = delivery["details"]["target_authority"]
        self.assertEqual(evidence["user_requested_visible_title"], ZHIYU_TITLE)
        self.assertEqual(evidence["user_requested_semantic_id"], ZHIYU)
        self.assertEqual(evidence["user_requested_native_thread_id"], ZHIYU_THREAD)
        self.assertEqual(evidence["target_lock_id"], lock.lock_id)
        self.assertEqual(evidence["resolved_semantic_id"], ZHIYU)
        self.assertEqual(evidence["resolved_native_thread_id"], "session_codex-peer")
        self.assertEqual(evidence["actual_recipient_id"], ZHIYU)
        self.assertTrue(evidence["allow_proxy"])

    # 7
    def test_only_an_explicit_allow_proxy_lock_may_use_a_proxy(self):
        self.engine.bind_agent(ZHIYU, "codex-peer")
        permissive = self.zhiyu_lock(allow_proxy=True)
        message = new_message(
            sender=CLAUDE_MAIN, recipient=ZHIYU, text="hello", target_lock=permissive
        )
        result = self.engine.deliver(message)
        self.assertNotIn(
            result.state,
            {
                DeliveryState.TARGET_AUTHORITY_MISMATCH,
                DeliveryState.EXACT_NATIVE_TARGET_NOT_BOUND,
            },
        )
        self.assertEqual(self.prompts(), 1)
        delivery = self.journal.get_delivery(message["message_id"], ZHIYU)
        self.assertTrue(delivery["details"]["target_authority"]["proxy_used"])

    # 8 (added: a lock is authority only while it stands)
    def test_revoked_lock_fails_closed(self):
        self.engine.bind_agent(ZHIYU, "codex-peer")
        lock = self.zhiyu_lock(allow_proxy=True)
        self.journal.revoke_target_lock(lock.lock_id, revoked_by="human:neo", reason="test")
        message = new_message(
            sender=CLAUDE_MAIN, recipient=ZHIYU, text="hello", target_lock=lock
        )
        result = self.engine.deliver(message)
        self.assertEqual(result.state, DeliveryState.TARGET_AUTHORITY_MISMATCH)
        self.assertEqual(result.details["reason"], "target_lock_revoked")
        self.assertEqual(self.prompts(), 0)


if __name__ == "__main__":
    unittest.main()
