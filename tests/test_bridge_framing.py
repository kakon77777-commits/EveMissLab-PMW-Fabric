from __future__ import annotations

from pathlib import Path
import re
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_bridge.core import BridgeEngine
from eml_bridge.framing import build_prompt_frame
from eml_bridge.journal import SQLiteJournal
from eml_bridge.message import new_message
from eml_bridge.mock_herdr import MockHerdrAdapter


SENDER = "agent://evemisslab/residence/claude-code"
RECIPIENT = "agent://evemisslab/research/codex-peer"


def reply_hint(frame: str) -> str:
    for line in frame.splitlines():
        if line.startswith("eml-bridge "):
            return line
    raise AssertionError(f"frame carries no eml-bridge reply hint:\n{frame}")


class ReplyHintTests(unittest.TestCase):
    """The hint the frame prints must be runnable exactly as printed.

    Round 5 (2026-08-22) found it was not. It omitted --db, and the default
    journal home ~/.evemisslab/herdr-bridge does not exist on the live host,
    so a recipient copying the hint verbatim writes its structured reply into
    a journal the controller never reads -- and the delivery then settles as
    `uncertain` for a reply that was in fact produced.
    """

    def setUp(self):
        self.message = new_message(sender=SENDER, recipient=RECIPIENT, text="hello")

    def test_hint_names_the_journal_the_controller_actually_reads(self):
        db = r"D:\example\fabric\runtime\bridge\bridge.sqlite3"
        self.assertIn(db, reply_hint(build_prompt_frame(self.message, RECIPIENT, journal_db=db)))

    def test_db_is_placed_before_the_subcommand(self):
        # argparse rejects a global option that appears after the subcommand.
        hint = reply_hint(build_prompt_frame(self.message, RECIPIENT, journal_db="/tmp/bridge.sqlite3"))
        self.assertLess(hint.index("--db"), hint.index(" reply "), hint)

    def test_path_with_spaces_stays_a_single_argument(self):
        db = r"D:\example-other\bridge.sqlite3"
        hint = reply_hint(build_prompt_frame(self.message, RECIPIENT, journal_db=db))
        self.assertIn(f'--db "{db}"', hint)

    def test_hint_never_suggests_an_encoding_lossy_input_flag(self):
        # --text loses non-ASCII to Windows argv; --stdin decodes with the console
        # locale (cp950 here). Only --text-file reads UTF-8 unconditionally.
        hint = reply_hint(build_prompt_frame(self.message, RECIPIENT))
        self.assertIn("--text-file", hint)
        self.assertNotRegex(hint, r"--text(?!-file)")
        self.assertNotIn("--stdin", hint)

    def test_without_a_journal_ref_the_hint_carries_no_dangling_db(self):
        hint = reply_hint(build_prompt_frame(self.message, RECIPIENT))
        self.assertNotIn("--db", hint)
        self.assertIn(" reply ", hint)

    def test_frame_still_closes_with_the_capture_token(self):
        # capture.py fences the recipient's turn on this exact closing token.
        frame = build_prompt_frame(self.message, RECIPIENT, journal_db="/tmp/bridge.sqlite3")
        self.assertTrue(frame.rstrip().endswith("[/EML-BRIDGE]"), frame)

    def test_frame_still_carries_the_marker_on_its_own_line(self):
        marker = self.message["payload"]["reply_marker"]
        frame = build_prompt_frame(self.message, RECIPIENT, journal_db="/tmp/bridge.sqlite3")
        self.assertRegex(frame, rf"(?m)^{re.escape(marker)}$")


class DeliveredFrameTests(unittest.TestCase):
    """Framing in isolation proves nothing: the engine has to pass its own path."""

    def test_engine_puts_its_own_journal_path_into_the_prompt_it_sends(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "sub dir" / "bridge.sqlite3"
            journal = SQLiteJournal(db)
            sent: list[str] = []

            def record(target: str, prompt: str) -> str:
                sent.append(prompt)
                return f"ok\n{re.search(r'(?m)^EML_REPLY_[A-Za-z0-9_-]+$', prompt).group(0)}\n"

            mock = MockHerdrAdapter(record)
            mock.add_agent("codex-peer", kind="codex")
            engine = BridgeEngine(journal=journal, herdr=mock, prompt_effect_timeout_ms=20, poll_interval_ms=1)
            try:
                engine.bind_agent(RECIPIENT, "codex-peer")
                lock = journal.create_target_lock(
                    requested_visible_title="Codex Peer",
                    requested_semantic_agent_id=RECIPIENT,
                    issued_by="test-controller",
                )
                engine.deliver(
                    new_message(sender=SENDER, recipient=RECIPIENT, text="hi", target_lock=lock)
                )
                self.assertEqual(len(sent), 1)
                self.assertIn(str(db), sent[0])
            finally:
                journal.close()

    def test_engine_emits_a_resolved_path_the_recipients_cwd_cannot_break(self):
        # The recipient runs the hint from its own pane's cwd, not the controller's.
        with tempfile.TemporaryDirectory() as tmp:
            unnormalized = Path(tmp) / "sub dir" / ".." / "sub dir" / "bridge.sqlite3"
            journal = SQLiteJournal(unnormalized)
            sent: list[str] = []

            def record(target: str, prompt: str) -> str:
                sent.append(prompt)
                return f"ok\n{re.search(r'(?m)^EML_REPLY_[A-Za-z0-9_-]+$', prompt).group(0)}\n"

            mock = MockHerdrAdapter(record)
            mock.add_agent("codex-peer", kind="codex")
            engine = BridgeEngine(journal=journal, herdr=mock, prompt_effect_timeout_ms=20, poll_interval_ms=1)
            try:
                engine.bind_agent(RECIPIENT, "codex-peer")
                lock = journal.create_target_lock(
                    requested_visible_title="Codex Peer",
                    requested_semantic_agent_id=RECIPIENT,
                    issued_by="test-controller",
                )
                engine.deliver(
                    new_message(sender=SENDER, recipient=RECIPIENT, text="hi", target_lock=lock)
                )
                hint = reply_hint(sent[0])
                self.assertIn(str(unnormalized.resolve()), hint)
                self.assertNotIn("..", hint)
            finally:
                journal.close()


if __name__ == "__main__":
    unittest.main()
