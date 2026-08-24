from __future__ import annotations

import re

from .models import CaptureConfidence, CaptureResult


# A pane narrower than the token hard-wraps it and re-indents the continuation,
# so the token is not contiguous in captured text. Only whitespace may bridge a
# break -- never other characters, or high-entropy markers would match prose.
_WRAP = r"(?:[ \t]*\r?\n[ \t]*)?"


def find_wrapped(text: str, token: str) -> tuple[int, int] | None:
    """Rightmost span of `token` in `text`, tolerating terminal hard-wrap.

    Returns None when absent. Contiguous matches are resolved without regex so
    the common case stays cheap.
    """
    if not token:
        return None
    index = text.rfind(token)
    if index >= 0:
        return index, index + len(token)
    pattern = _WRAP.join(re.escape(ch) for ch in token)
    last = None
    for last in re.finditer(pattern, text):
        pass
    return (last.start(), last.end()) if last else None


def terminal_delta(before: str, after: str) -> tuple[str, str]:
    """Best-effort extraction of newly visible terminal text.

    Terminal UIs may redraw or truncate history, so this is evidence handling,
    not a claim that screen text is an append-only log.
    """
    if not before:
        return after, "no_baseline"
    if after.startswith(before):
        return after[len(before):], "prefix"

    # Scrollback truncation often leaves a suffix of the previous read as the
    # prefix of the next read. Find the largest exact overlap.
    limit = min(len(before), len(after), 32768)
    for width in range(limit, 31, -1):
        if before[-width:] == after[:width]:
            return after[width:], "suffix_prefix_overlap"

    # A redraw may preserve a large common prefix but replace the tail.
    common = 0
    max_common = min(len(before), len(after))
    while common < max_common and before[common] == after[common]:
        common += 1
    if common >= 64:
        return after[common:], "common_prefix_redraw"

    return after, "unresolved_redraw"


def capture_reply(
    before: str,
    after: str,
    reply_marker: str,
    *,
    structured_text: str | None = None,
) -> CaptureResult:
    if structured_text is not None:
        return CaptureResult(
            text=structured_text.strip(),
            confidence=CaptureConfidence.STRUCTURED,
            evidence={"source": "structured_reply"},
        )

    delta, delta_mode = terminal_delta(before, after)
    close_span = find_wrapped(delta, "[/EML-BRIDGE]")
    tail = delta[close_span[1]:] if close_span else delta

    # Strong terminal fence: marker appears after the echoed bridge frame.
    marker_span = find_wrapped(tail, reply_marker)
    if marker_span:
        candidate = tail[: marker_span[0]].strip()
        if candidate:
            return CaptureResult(
                text=candidate,
                confidence=CaptureConfidence.TURN_FENCED,
                evidence={
                    "source": "terminal",
                    "delta_mode": delta_mode,
                    "marker_after_frame": close_span is not None,
                    "marker_wrapped": tail.rfind(reply_marker) < 0,
                },
            )

    # If the frame itself is not visible (alternate-screen redraw), a final
    # marker can still be useful, but it is explicitly downgraded.
    marker_span = find_wrapped(delta, reply_marker)
    if marker_span:
        candidate = delta[: marker_span[0]].strip()
        if candidate and "BEGIN_MESSAGE" not in candidate[-2000:]:
            return CaptureResult(
                text=candidate,
                confidence=CaptureConfidence.HEURISTIC,
                evidence={
                    "source": "terminal",
                    "delta_mode": delta_mode,
                    "reason": "marker_without_visible_frame_boundary",
                    "marker_wrapped": delta.rfind(reply_marker) < 0,
                },
            )

    candidate = tail.strip()
    if candidate:
        return CaptureResult(
            text=candidate,
            confidence=CaptureConfidence.HEURISTIC,
            evidence={
                "source": "terminal",
                "delta_mode": delta_mode,
                "reason": "no_reply_marker",
            },
        )

    return CaptureResult(
        text=None,
        confidence=CaptureConfidence.NONE,
        evidence={"source": "terminal", "delta_mode": delta_mode, "reason": "empty_delta"},
    )
