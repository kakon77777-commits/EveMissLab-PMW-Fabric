from __future__ import annotations

import json
from pathlib import Path
from typing import Protocol

from .models import now_iso


class BoardSink(Protocol):
    def record_message(self, message: dict, delivery: dict | None = None) -> str | None: ...


class ProvenanceSink(Protocol):
    def stamp(self, event_type: str, payload: dict) -> str | None: ...


class NullBoardSink:
    def record_message(self, message: dict, delivery: dict | None = None) -> str | None:
        return None


class NullProvenanceSink:
    def stamp(self, event_type: str, payload: dict) -> str | None:
        return None


class JsonlBoardSink:
    """Local development stand-in. This is not the canonical AI Board API."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record_message(self, message: dict, delivery: dict | None = None) -> str | None:
        record = {"recorded_at": now_iso(), "message": message, "delivery": delivery}
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return f"jsonl://{self.path.name}#{message['message_id']}"


class JsonlProvenanceSink:
    """Local evidence sink; intentionally not branded as a CTCL implementation."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def stamp(self, event_type: str, payload: dict) -> str | None:
        import hashlib

        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        record = {
            "recorded_at": now_iso(),
            "event_type": event_type,
            "sha256": digest,
            "payload": payload,
        }
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
        return f"local-proof://sha256/{digest}"
