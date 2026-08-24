from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from eml_bridge.capture import capture_reply
from eml_bridge.models import CaptureConfidence


MARKER = "EML_REPLY_msg_fba2591151214c39a5e76173486f4dea_23a6cc180d09"


def wrapped(token: str, width: int, indent: str = "  ") -> str:
    """Reproduce a hard-wrapping TUI: fixed columns, re-indented continuations."""
    body = indent + token
    out = []
    while len(body) > width:
        out.append(body[:width])
        body = indent + body[width:]
    out.append(body)
    return "\n".join(out)


class WrappedMarkerCaptureTests(unittest.TestCase):
    """A marker longer than the pane is never contiguous in the captured text.

    Live finding, 2026-08-22: every pane in the `evemisslab-pmw` session is
    narrower (27 cols, 54 zoomed) than a reply marker (58 chars), so Herdr
    returns the token split across lines even with `--source recent-unwrapped`.
    Both marker paths in capture_reply used str.rfind, so the protocol's own
    documented terminal fallback could not fire on this host at all -- round 1
    (Codex -> Claude) and round 6 (Claude -> Codex) both died this way.
    """

    def setUp(self):
        self.before = "ready\n"
        self.frame = f"BEGIN_MESSAGE\nhello\nEND_MESSAGE\nappend:\n{MARKER}\n[/EML-BRIDGE]\n"

    def test_hard_wrapped_marker_after_the_frame_still_fences_the_turn(self):
        after = self.before + self.frame + "  actual answer\n" + wrapped(MARKER, 50) + "\n"
        result = capture_reply(self.before, after, MARKER)
        self.assertEqual(result.confidence, CaptureConfidence.TURN_FENCED)
        self.assertEqual(result.text, "actual answer")

    def test_contiguous_marker_is_unaffected(self):
        after = self.before + self.frame + "actual answer\n" + MARKER + "\n"
        result = capture_reply(self.before, after, MARKER)
        self.assertEqual(result.confidence, CaptureConfidence.TURN_FENCED)
        self.assertEqual(result.text, "actual answer")

    def test_wrapped_echo_alone_is_still_not_an_acknowledgement(self):
        # The frame itself carries the marker; echoing it proves nothing.
        echoed = f"BEGIN_MESSAGE\nhello\nEND_MESSAGE\nappend:\n{wrapped(MARKER, 50)}\n[/EML-BRIDGE]\n"
        result = capture_reply(self.before, self.before + echoed, MARKER)
        self.assertNotEqual(result.confidence, CaptureConfidence.TURN_FENCED)

    def test_marker_characters_scattered_through_prose_do_not_match(self):
        # Wrap tolerance must span whitespace only, never arbitrary text.
        scattered = " x ".join(MARKER)
        after = self.before + self.frame + "actual answer\n" + scattered + "\n"
        result = capture_reply(self.before, after, MARKER)
        self.assertNotEqual(result.confidence, CaptureConfidence.TURN_FENCED)

    def test_wrapped_close_token_still_locates_the_frame_boundary(self):
        # [/EML-BRIDGE] is short, but a 14-column pane splits it too.
        frame = f"BEGIN_MESSAGE\nhello\nEND_MESSAGE\nappend:\n{MARKER}\n{wrapped('[/EML-BRIDGE]', 10)}\n"
        after = self.before + frame + "actual answer\n" + MARKER + "\n"
        result = capture_reply(self.before, after, MARKER)
        self.assertEqual(result.confidence, CaptureConfidence.TURN_FENCED)
        self.assertEqual(result.text, "actual answer")

    def test_wrapped_marker_without_a_visible_frame_records_that_absence(self):
        # Alternate-screen redraw: no frame in the delta, only the marker.
        #
        # Pinning pre-existing behaviour, not endorsing it. capture.py's comment
        # says a marker with no visible frame "is explicitly downgraded", but the
        # HEURISTIC branch is only reachable when the tail candidate is empty, so
        # this case still returns TURN_FENCED and records the absence in evidence
        # instead. Wrap tolerance must not silently change which of the two fires.
        after = self.before + "  actual answer\n" + wrapped(MARKER, 50) + "\n"
        result = capture_reply(self.before, after, MARKER)
        self.assertEqual(result.confidence, CaptureConfidence.TURN_FENCED)
        self.assertIs(result.evidence.get("marker_after_frame"), False)
        self.assertIs(result.evidence.get("marker_wrapped"), True)
        self.assertEqual(result.text, "actual answer")

    def test_contiguous_marker_without_a_frame_takes_the_same_path(self):
        # The pre-fix code did exactly this too; the wrapped case must match it.
        after = self.before + "actual answer\n" + MARKER + "\n"
        result = capture_reply(self.before, after, MARKER)
        self.assertEqual(result.confidence, CaptureConfidence.TURN_FENCED)
        self.assertIs(result.evidence.get("marker_after_frame"), False)
        self.assertIs(result.evidence.get("marker_wrapped"), False)

    def test_structured_reply_still_outranks_any_terminal_evidence(self):
        after = self.before + self.frame + "noise\n" + wrapped(MARKER, 50) + "\n"
        result = capture_reply(self.before, after, MARKER, structured_text="the real reply")
        self.assertEqual(result.confidence, CaptureConfidence.STRUCTURED)
        self.assertEqual(result.text, "the real reply")


if __name__ == "__main__":
    unittest.main()
