from __future__ import annotations

import hashlib

from .ids import new_id
from .models import TargetLock, now_iso


def payload_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _target_authority(
    *,
    recipient: str,
    target_lock: TargetLock | None,
    authority_mode: str | None,
    parent_authority: dict | None,
    parent_message_id: str | None,
) -> dict:
    """The requested layer of the audit trail.

    ``resolved_*`` stay null here; only the engine may fill them, and only from a
    live binding. Keeping requested and resolved in separate hands is the whole
    point: otherwise a sender could assert its own resolution.
    """
    block: dict[str, object] = {
        "mode": "unlocked",
        "target_lock_id": None,
        "user_requested_visible_title": None,
        "user_requested_semantic_id": None,
        "user_requested_native_thread_id": None,
        "allow_proxy": False,
        "actual_recipient_id": recipient,
        "resolved_semantic_id": None,
        "resolved_native_thread_id": None,
    }
    if target_lock is not None:
        block.update(
            {
                "mode": "locked",
                "target_lock_id": target_lock.lock_id,
                "user_requested_visible_title": target_lock.requested_visible_title,
                "user_requested_semantic_id": target_lock.requested_semantic_agent_id,
                "user_requested_native_thread_id": target_lock.requested_native_thread_id,
                "allow_proxy": bool(target_lock.allow_proxy),
            }
        )
        return block
    if authority_mode == "parent_derived":
        block.update(
            {
                "mode": "parent_derived",
                "derived_from_message_id": parent_message_id,
                "target_lock_id": (parent_authority or {}).get("target_lock_id"),
                "user_requested_semantic_id": recipient,
            }
        )
        return block
    if authority_mode is not None:
        block["mode"] = authority_mode
    return block


def new_message(
    *,
    sender: str,
    recipient: str,
    text: str,
    kind: str = "request",
    route_intent: str = "direct",
    thread_id: str | None = None,
    correlation_id: str | None = None,
    parent_message_id: str | None = None,
    timeout_ms: int = 120_000,
    require_semantic_ack: bool = True,
    projection: str = "herdr_prompt",
    max_hops: int = 8,
    auto_reply_depth: int = 0,
    max_auto_reply_depth: int = 6,
    origin: str = "agent",
    target_lock: TargetLock | None = None,
    authority_mode: str | None = None,
    parent_authority: dict | None = None,
) -> dict:
    message_id = new_id("msg")
    authority = _target_authority(
        recipient=recipient,
        target_lock=target_lock,
        authority_mode=authority_mode,
        parent_authority=parent_authority,
        parent_message_id=parent_message_id,
    )
    thread_id = thread_id or new_id("thr")
    correlation_id = correlation_id or new_id("corr")
    marker = f"EML_REPLY_{message_id}_{new_id('r')[-12:]}"
    text_hash = payload_hash(text)
    now = now_iso()
    return {
        "protocol": "eml-herdr-bridge",
        "version": "0.1",
        "message_id": message_id,
        "thread_id": thread_id,
        "correlation_id": correlation_id,
        "parent_message_id": parent_message_id,
        "kind": kind,
        "route_intent": route_intent,
        "sender": {"semantic_agent_id": sender},
        "recipients": [{"semantic_agent_id": recipient}],
        "target_authority": authority,
        "payload": {
            "content_type": "text/markdown",
            "text": text,
            "trust": "internal",
            "reply_marker": marker,
            "artifact_refs": [],
        },
        "delivery": {
            "projection": projection,
            "strict_turn": True,
            "require_semantic_ack": require_semantic_ack,
            "wait_until": ["idle", "done", "blocked"],
            "timeout_ms": int(timeout_ms),
        },
        "routing": {
            "hop_count": 0,
            "max_hops": int(max_hops),
            "auto_reply_depth": int(auto_reply_depth),
            "max_auto_reply_depth": int(max_auto_reply_depth),
            "route_trace": [sender],
            "idempotency_key": new_id("idem"),
            "payload_hash": text_hash,
        },
        "provenance": {
            "created_at": now,
            "observed_at": now,
            "recorded_at": now,
            "origin": origin,
        },
    }


def reply_message(parent: dict, *, sender: str, text: str, timeout_ms: int = 120_000) -> dict:
    recipient = parent["sender"]["semantic_agent_id"]
    depth = int(parent["routing"].get("auto_reply_depth", 0)) + 1
    message = new_message(
        sender=sender,
        recipient=recipient,
        text=text,
        kind="reply",
        route_intent="reply",
        thread_id=parent["thread_id"],
        correlation_id=parent["correlation_id"],
        parent_message_id=parent["message_id"],
        timeout_ms=timeout_ms,
        require_semantic_ack=False,
        authority_mode="parent_derived",
        parent_authority=parent.get("target_authority"),
        max_hops=int(parent["routing"].get("max_hops", 8)),
        auto_reply_depth=depth,
        max_auto_reply_depth=int(parent["routing"].get("max_auto_reply_depth", 6)),
    )
    message["routing"]["hop_count"] = int(parent["routing"].get("hop_count", 0)) + 1
    message["routing"]["route_trace"] = list(parent["routing"].get("route_trace", [])) + [sender]
    return message
