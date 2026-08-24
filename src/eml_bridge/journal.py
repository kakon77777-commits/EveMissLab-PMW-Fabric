from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .ids import new_id
from .models import ALLOWED_TRANSITIONS, AgentBinding, DeliveryState, TargetLock, now_iso


class SQLiteJournal:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path, timeout=10.0, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self._migrate()

    def close(self) -> None:
        self.conn.close()

    def _migrate(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agents (
                semantic_agent_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                role TEXT,
                binding_json TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                correlation_id TEXT NOT NULL,
                parent_message_id TEXT,
                kind TEXT NOT NULL,
                route_intent TEXT NOT NULL,
                sender_id TEXT NOT NULL,
                recipient_id TEXT NOT NULL,
                idempotency_key TEXT NOT NULL UNIQUE,
                payload_hash TEXT NOT NULL,
                message_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_messages_thread ON messages(thread_id, created_at);

            CREATE TABLE IF NOT EXISTS deliveries (
                message_id TEXT NOT NULL,
                recipient_id TEXT NOT NULL,
                state TEXT NOT NULL,
                history_json TEXT NOT NULL,
                capture_confidence TEXT,
                reply_text TEXT,
                details_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY(message_id, recipient_id),
                FOREIGN KEY(message_id) REFERENCES messages(message_id)
            );

            CREATE TABLE IF NOT EXISTS route_fingerprints (
                sender_id TEXT NOT NULL,
                recipient_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                message_id TEXT NOT NULL,
                recorded_at TEXT NOT NULL,
                PRIMARY KEY(sender_id, recipient_id, thread_id, payload_hash)
            );

            CREATE TABLE IF NOT EXISTS structured_replies (
                parent_message_id TEXT NOT NULL,
                author_id TEXT NOT NULL,
                reply_message_id TEXT,
                text TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(parent_message_id, author_id)
            );

            CREATE TABLE IF NOT EXISTS target_locks (
                lock_id TEXT PRIMARY KEY,
                requested_visible_title TEXT NOT NULL,
                requested_semantic_agent_id TEXT NOT NULL,
                requested_native_thread_id TEXT,
                issued_by TEXT NOT NULL,
                issued_at TEXT NOT NULL,
                allow_proxy INTEGER NOT NULL DEFAULT 0,
                revoked_at TEXT,
                revoked_by TEXT,
                revocation_reason TEXT
            );
            CREATE INDEX IF NOT EXISTS idx_target_locks_semantic
                ON target_locks(requested_semantic_agent_id);

            CREATE TABLE IF NOT EXISTS runtime_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                semantic_agent_id TEXT,
                message_id TEXT,
                payload_json TEXT NOT NULL,
                recorded_at TEXT NOT NULL
            );
            """
        )

    def get_meta(self, key: str) -> str | None:
        row = self.conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return None if row is None else str(row["value"])

    def set_meta(self, key: str, value: str) -> None:
        self.conn.execute(
            "INSERT INTO meta(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )

    def upsert_agent(self, binding: AgentBinding) -> None:
        self.conn.execute(
            """
            INSERT INTO agents(semantic_agent_id, display_name, role, binding_json, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(semantic_agent_id) DO UPDATE SET
                display_name=excluded.display_name,
                role=excluded.role,
                binding_json=excluded.binding_json,
                updated_at=excluded.updated_at
            """,
            (
                binding.semantic_agent_id,
                binding.display_name,
                binding.role,
                json.dumps(binding.to_dict(), ensure_ascii=False, sort_keys=True),
                now_iso(),
            ),
        )

    def get_agent(self, semantic_agent_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT display_name, role, binding_json FROM agents WHERE semantic_agent_id=?",
            (semantic_agent_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "semantic_agent_id": semantic_agent_id,
            "display_name": row["display_name"],
            "role": row["role"],
            "runtime_binding": json.loads(row["binding_json"]),
        }

    def list_agents(self) -> list[dict[str, Any]]:
        rows = self.conn.execute("SELECT semantic_agent_id FROM agents ORDER BY semantic_agent_id").fetchall()
        return [self.get_agent(str(row["semantic_agent_id"])) for row in rows]

    def journal_message(self, message: dict) -> str:
        recipient = message["recipients"][0]["semantic_agent_id"]
        raw = json.dumps(message, ensure_ascii=False, sort_keys=True)
        try:
            self.conn.execute(
                """
                INSERT INTO messages(
                    message_id, thread_id, correlation_id, parent_message_id, kind, route_intent,
                    sender_id, recipient_id, idempotency_key, payload_hash, message_json, created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    message["message_id"],
                    message["thread_id"],
                    message["correlation_id"],
                    message.get("parent_message_id"),
                    message["kind"],
                    message["route_intent"],
                    message["sender"]["semantic_agent_id"],
                    recipient,
                    message["routing"]["idempotency_key"],
                    message["routing"]["payload_hash"],
                    raw,
                    message["provenance"]["created_at"],
                ),
            )
            return message["message_id"]
        except sqlite3.IntegrityError as exc:
            row = self.conn.execute(
                "SELECT message_id, message_json FROM messages WHERE idempotency_key=?",
                (message["routing"]["idempotency_key"],),
            ).fetchone()
            if row is not None and row["message_json"] == raw:
                return str(row["message_id"])
            raise ValueError("idempotency key already exists with different message content") from exc

    def get_message(self, message_id: str) -> dict[str, Any] | None:
        row = self.conn.execute("SELECT message_json FROM messages WHERE message_id=?", (message_id,)).fetchone()
        return None if row is None else json.loads(row["message_json"])

    def list_thread(self, thread_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            "SELECT message_json FROM messages WHERE thread_id=? ORDER BY created_at, rowid",
            (thread_id,),
        ).fetchall()
        return [json.loads(row["message_json"]) for row in rows]

    def ensure_delivery(self, message_id: str, recipient_id: str) -> None:
        now = now_iso()
        history = [{"state": DeliveryState.JOURNALED.value, "at": now, "details": {}}]
        self.conn.execute(
            """
            INSERT OR IGNORE INTO deliveries(
                message_id, recipient_id, state, history_json, details_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                message_id,
                recipient_id,
                DeliveryState.JOURNALED.value,
                json.dumps(history, ensure_ascii=False),
                "{}",
                now,
                now,
            ),
        )

    def get_delivery(self, message_id: str, recipient_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM deliveries WHERE message_id=? AND recipient_id=?",
            (message_id, recipient_id),
        ).fetchone()
        if row is None:
            return None
        return {
            "message_id": row["message_id"],
            "recipient_id": row["recipient_id"],
            "state": row["state"],
            "history": json.loads(row["history_json"]),
            "capture_confidence": row["capture_confidence"],
            "reply_text": row["reply_text"],
            "details": json.loads(row["details_json"]),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    def transition_delivery(
        self,
        message_id: str,
        recipient_id: str,
        target: DeliveryState,
        *,
        details: dict[str, Any] | None = None,
        reply_text: str | None = None,
        capture_confidence: str | None = None,
    ) -> dict[str, Any]:
        current = self.get_delivery(message_id, recipient_id)
        if current is None:
            raise KeyError(f"delivery not found: {message_id} -> {recipient_id}")
        state = DeliveryState(current["state"])
        if target != state:
            allowed = ALLOWED_TRANSITIONS.get(state, set())
            if target not in allowed:
                raise ValueError(f"illegal delivery transition: {state.value} -> {target.value}")
        merged = dict(current["details"])
        if details:
            merged.update(details)
        history = list(current["history"])
        history.append({"state": target.value, "at": now_iso(), "details": details or {}})
        self.conn.execute(
            """
            UPDATE deliveries SET state=?, history_json=?, capture_confidence=COALESCE(?, capture_confidence),
                reply_text=COALESCE(?, reply_text), details_json=?, updated_at=?
            WHERE message_id=? AND recipient_id=?
            """,
            (
                target.value,
                json.dumps(history, ensure_ascii=False),
                capture_confidence,
                reply_text,
                json.dumps(merged, ensure_ascii=False, sort_keys=True),
                now_iso(),
                message_id,
                recipient_id,
            ),
        )
        return self.get_delivery(message_id, recipient_id)

    def route_seen(self, sender_id: str, recipient_id: str, thread_id: str, payload_hash: str) -> bool:
        row = self.conn.execute(
            """SELECT 1 FROM route_fingerprints
               WHERE sender_id=? AND recipient_id=? AND thread_id=? AND payload_hash=?""",
            (sender_id, recipient_id, thread_id, payload_hash),
        ).fetchone()
        return row is not None

    def record_route(self, sender_id: str, recipient_id: str, thread_id: str, payload_hash: str, message_id: str) -> None:
        self.conn.execute(
            """
            INSERT OR IGNORE INTO route_fingerprints(sender_id,recipient_id,thread_id,payload_hash,message_id,recorded_at)
            VALUES(?,?,?,?,?,?)
            """,
            (sender_id, recipient_id, thread_id, payload_hash, message_id, now_iso()),
        )

    def record_structured_reply(
        self,
        parent_message_id: str,
        author_id: str,
        text: str,
        *,
        reply_message_id: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO structured_replies(parent_message_id,author_id,reply_message_id,text,created_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(parent_message_id,author_id) DO UPDATE SET
              reply_message_id=excluded.reply_message_id,
              text=excluded.text,
              created_at=excluded.created_at
            """,
            (parent_message_id, author_id, reply_message_id, text, now_iso()),
        )

    def get_structured_reply(self, parent_message_id: str, author_id: str) -> dict[str, Any] | None:
        row = self.conn.execute(
            "SELECT * FROM structured_replies WHERE parent_message_id=? AND author_id=?",
            (parent_message_id, author_id),
        ).fetchone()
        return None if row is None else dict(row)

    def create_target_lock(
        self,
        *,
        requested_visible_title: str,
        requested_semantic_agent_id: str,
        issued_by: str,
        requested_native_thread_id: str | None = None,
        allow_proxy: bool = False,
        lock_id: str | None = None,
    ) -> TargetLock:
        lock = TargetLock(
            lock_id=lock_id or new_id("lock"),
            requested_visible_title=requested_visible_title,
            requested_semantic_agent_id=requested_semantic_agent_id,
            requested_native_thread_id=requested_native_thread_id,
            issued_by=issued_by,
            issued_at=now_iso(),
            allow_proxy=bool(allow_proxy),
        )
        self.conn.execute(
            """
            INSERT INTO target_locks(
                lock_id, requested_visible_title, requested_semantic_agent_id,
                requested_native_thread_id, issued_by, issued_at, allow_proxy
            ) VALUES(?,?,?,?,?,?,?)
            """,
            (
                lock.lock_id,
                lock.requested_visible_title,
                lock.requested_semantic_agent_id,
                lock.requested_native_thread_id,
                lock.issued_by,
                lock.issued_at,
                1 if lock.allow_proxy else 0,
            ),
        )
        self.record_event(
            "target_lock.issued",
            lock.to_dict(),
            semantic_agent_id=lock.requested_semantic_agent_id,
        )
        return lock

    @staticmethod
    def _lock_from_row(row: sqlite3.Row) -> TargetLock:
        return TargetLock(
            lock_id=str(row["lock_id"]),
            requested_visible_title=str(row["requested_visible_title"]),
            requested_semantic_agent_id=str(row["requested_semantic_agent_id"]),
            requested_native_thread_id=row["requested_native_thread_id"],
            issued_by=str(row["issued_by"]),
            issued_at=str(row["issued_at"]),
            allow_proxy=bool(row["allow_proxy"]),
            revoked_at=row["revoked_at"],
            revoked_by=row["revoked_by"],
            revocation_reason=row["revocation_reason"],
        )

    def get_target_lock(self, lock_id: str) -> TargetLock | None:
        row = self.conn.execute("SELECT * FROM target_locks WHERE lock_id=?", (lock_id,)).fetchone()
        return None if row is None else self._lock_from_row(row)

    def list_target_locks(self) -> list[TargetLock]:
        rows = self.conn.execute("SELECT * FROM target_locks ORDER BY issued_at, lock_id").fetchall()
        return [self._lock_from_row(row) for row in rows]

    def revoke_target_lock(self, lock_id: str, *, revoked_by: str, reason: str | None = None) -> TargetLock:
        lock = self.get_target_lock(lock_id)
        if lock is None:
            raise KeyError(f"target lock not found: {lock_id}")
        if lock.is_revoked:
            return lock
        self.conn.execute(
            "UPDATE target_locks SET revoked_at=?, revoked_by=?, revocation_reason=? WHERE lock_id=?",
            (now_iso(), revoked_by, reason, lock_id),
        )
        revoked = self.get_target_lock(lock_id)
        assert revoked is not None
        self.record_event(
            "target_lock.revoked",
            revoked.to_dict(),
            semantic_agent_id=revoked.requested_semantic_agent_id,
        )
        return revoked

    def record_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        semantic_agent_id: str | None = None,
        message_id: str | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO runtime_events(event_type,semantic_agent_id,message_id,payload_json,recorded_at) VALUES(?,?,?,?,?)",
            (
                event_type,
                semantic_agent_id,
                message_id,
                json.dumps(payload, ensure_ascii=False, sort_keys=True),
                now_iso(),
            ),
        )
