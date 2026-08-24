from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from .core import BridgeEngine
from .herdr import HerdrCLIAdapter
from .journal import SQLiteJournal
from .message import new_message, reply_message
from .mock_herdr import MockHerdrAdapter
from .sinks import JsonlBoardSink, JsonlProvenanceSink, NullBoardSink, NullProvenanceSink


def _read_text(args: argparse.Namespace) -> str:
    if getattr(args, "text", None) is not None:
        return args.text
    if getattr(args, "text_file", None):
        return Path(args.text_file).read_text(encoding="utf-8")
    if getattr(args, "stdin", False):
        return sys.stdin.read()
    raise SystemExit("one of --text, --text-file, or --stdin is required")


def _engine(args: argparse.Namespace, *, mock: MockHerdrAdapter | None = None) -> tuple[BridgeEngine, SQLiteJournal]:
    journal = SQLiteJournal(args.db)
    herdr = mock or HerdrCLIAdapter(binary=args.herdr_bin, socket_path=args.socket_path)
    board = JsonlBoardSink(args.board_jsonl) if args.board_jsonl else NullBoardSink()
    proof = JsonlProvenanceSink(args.proof_jsonl) if args.proof_jsonl else NullProvenanceSink()
    engine = BridgeEngine(
        journal=journal,
        herdr=herdr,
        board_sink=board,
        provenance_sink=proof,
        prompt_effect_timeout_ms=args.effect_timeout_ms,
        poll_interval_ms=args.poll_interval_ms,
        allow_heuristic_capture=args.allow_heuristic_capture,
    )
    return engine, journal


def _print(value: object) -> None:
    text = json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        text.encode(encoding)
    except (LookupError, UnicodeEncodeError):
        text = json.dumps(value, ensure_ascii=True, indent=2, sort_keys=True)
    print(text)


def cmd_bind(args: argparse.Namespace) -> int:
    engine, journal = _engine(args)
    try:
        binding = engine.bind_agent(
            args.semantic_id,
            args.target,
            display_name=args.display_name,
            role=args.role,
            herdr_session=args.herdr_session,
        )
        _print(binding.to_dict())
        return 0
    finally:
        journal.close()


def cmd_agents(args: argparse.Namespace) -> int:
    _, journal = _engine(args)
    try:
        _print(journal.list_agents())
        return 0
    finally:
        journal.close()


def cmd_lock_create(args: argparse.Namespace) -> int:
    _, journal = _engine(args)
    try:
        lock = journal.create_target_lock(
            requested_visible_title=args.visible_title,
            requested_semantic_agent_id=args.semantic_id,
            requested_native_thread_id=args.native_thread_id,
            issued_by=args.issued_by,
            allow_proxy=args.allow_proxy,
        )
        _print(lock.to_dict())
        return 0
    finally:
        journal.close()


def cmd_lock_list(args: argparse.Namespace) -> int:
    _, journal = _engine(args)
    try:
        _print([lock.to_dict() for lock in journal.list_target_locks()])
        return 0
    finally:
        journal.close()


def cmd_lock_revoke(args: argparse.Namespace) -> int:
    _, journal = _engine(args)
    try:
        lock = journal.revoke_target_lock(args.lock_id, revoked_by=args.by, reason=args.reason)
        _print(lock.to_dict())
        return 0
    finally:
        journal.close()


def cmd_send(args: argparse.Namespace) -> int:
    text = _read_text(args)
    engine, journal = _engine(args)
    try:
        lock = journal.get_target_lock(args.target_lock)
        if lock is None:
            raise SystemExit(f"target lock not found: {args.target_lock}")
        # --to is an assertion, never a choice. A mismatch still builds the message so
        # the refusal lands in the journal as evidence, instead of vanishing at the CLI.
        recipient = args.recipient or lock.requested_semantic_agent_id
        message = new_message(
            sender=args.sender,
            recipient=recipient,
            text=text,
            target_lock=lock,
            route_intent=args.intent,
            thread_id=args.thread,
            correlation_id=args.correlation,
            timeout_ms=args.timeout_ms,
            require_semantic_ack=not args.no_ack,
            projection=args.projection,
        )
        result = engine.deliver(message)
        _print({"message": message, "delivery": result.to_dict()})
        return 0 if result.state.value in {"acknowledged", "reply_captured", "runtime_settled"} else 1
    finally:
        journal.close()


def cmd_reply(args: argparse.Namespace) -> int:
    text = _read_text(args)
    engine, journal = _engine(args)
    try:
        parent = journal.get_message(args.parent_message_id)
        if parent is None:
            raise SystemExit(f"parent message not found: {args.parent_message_id}")
        recipients = {x["semantic_agent_id"] for x in parent["recipients"]}
        if args.sender not in recipients:
            raise SystemExit("--from agent is not a recipient of the parent message")
        message = reply_message(parent, sender=args.sender, text=text, timeout_ms=args.timeout_ms)
        journal.journal_message(message)
        journal.record_structured_reply(
            args.parent_message_id,
            args.sender,
            text,
            reply_message_id=message["message_id"],
        )
        output: dict[str, object] = {"structured_reply": message}
        if args.deliver:
            output["delivery"] = engine.deliver(message).to_dict()
        _print(output)
        return 0
    finally:
        journal.close()


def cmd_thread(args: argparse.Namespace) -> int:
    _, journal = _engine(args)
    try:
        _print(journal.list_thread(args.thread_id))
        return 0
    finally:
        journal.close()


def cmd_reconcile(args: argparse.Namespace) -> int:
    engine, journal = _engine(args)
    try:
        if args.new_epoch:
            engine.rotate_runtime_epoch()
        _print({"runtime_epoch_id": engine.runtime_epoch_id, "agents": engine.reconcile_all()})
        return 0
    finally:
        journal.close()


def cmd_demo(args: argparse.Namespace) -> int:
    from .demo import run_demo

    result = run_demo(Path(args.demo_dir))
    _print(result)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="eml-bridge", description="EveMissLab Herdr Bridge Runtime MVP v0.1")
    default_root = Path(os.environ.get("EML_BRIDGE_HOME", str(Path.home() / ".evemisslab" / "herdr-bridge")))
    p.add_argument("--db", default=str(default_root / "bridge.sqlite3"))
    p.add_argument("--herdr-bin", default=os.environ.get("HERDR_BIN", "herdr"))
    p.add_argument("--socket-path", default=os.environ.get("HERDR_SOCKET_PATH"))
    p.add_argument("--board-jsonl", default=None, help="development mirror; not the canonical AI Board API")
    p.add_argument("--proof-jsonl", default=None, help="development evidence sink; not CTCL")
    p.add_argument("--effect-timeout-ms", type=int, default=5000)
    p.add_argument("--poll-interval-ms", type=int, default=100)
    p.add_argument("--allow-heuristic-capture", action="store_true")

    sub = p.add_subparsers(dest="command", required=True)

    b = sub.add_parser("bind", help="bind a semantic identity to a live Herdr agent target")
    b.add_argument("semantic_id")
    b.add_argument("target")
    b.add_argument("--display-name")
    b.add_argument("--role")
    b.add_argument("--herdr-session", default="default")
    b.set_defaults(func=cmd_bind)

    a = sub.add_parser("agents", help="list semantic identities in the bridge journal")
    a.set_defaults(func=cmd_agents)

    s = sub.add_parser("send", help="send one strict-turn message through Herdr")
    s.add_argument("--from", dest="sender", required=True)
    s.add_argument(
        "--target-lock",
        required=True,
        help="issued target lock id; the recipient is derived from it (fail closed without one)",
    )
    s.add_argument(
        "--to",
        dest="recipient",
        default=None,
        help="optional assertion only; must equal the lock's semantic id or the send is refused",
    )
    g = s.add_mutually_exclusive_group(required=True)
    g.add_argument("--text")
    g.add_argument("--text-file")
    g.add_argument("--stdin", action="store_true")
    s.add_argument("--intent", default="direct", choices=["direct", "reply", "delegate", "broadcast", "notice"])
    s.add_argument("--thread")
    s.add_argument("--correlation")
    s.add_argument("--timeout-ms", type=int, default=120000)
    s.add_argument("--projection", default="herdr_prompt", choices=["herdr_prompt", "board_and_prompt", "board_only"])
    s.add_argument("--no-ack", action="store_true")
    s.set_defaults(func=cmd_send)

    r = sub.add_parser("reply", help="record a structured reply to a bridge message")
    r.add_argument("parent_message_id")
    r.add_argument("--from", dest="sender", required=True)
    rg = r.add_mutually_exclusive_group(required=True)
    rg.add_argument("--text")
    rg.add_argument("--text-file")
    rg.add_argument("--stdin", action="store_true")
    r.add_argument("--timeout-ms", type=int, default=120000)
    r.add_argument("--deliver", action="store_true", help="also prompt the parent sender; off by default to avoid self-deadlock")
    r.set_defaults(func=cmd_reply)

    lk = sub.add_parser("lock", help="manage target locks (recipient authority)")
    lksub = lk.add_subparsers(dest="lock_command", required=True)

    lkc = lksub.add_parser("create", help="issue a target lock; controller/human workflow only")
    lkc.add_argument("--visible-title", required=True)
    lkc.add_argument("--semantic-id", required=True)
    lkc.add_argument("--native-thread-id", default=None)
    lkc.add_argument("--issued-by", required=True)
    lkc.add_argument(
        "--allow-proxy",
        action="store_true",
        help="permit a stand-in runtime for the locked identity; deliberate act, default off",
    )
    lkc.set_defaults(func=cmd_lock_create)

    lkl = lksub.add_parser("list", help="list issued target locks")
    lkl.set_defaults(func=cmd_lock_list)

    lkr = lksub.add_parser("revoke", help="revoke a target lock")
    lkr.add_argument("lock_id")
    lkr.add_argument("--by", required=True)
    lkr.add_argument("--reason", default=None)
    lkr.set_defaults(func=cmd_lock_revoke)

    t = sub.add_parser("thread", help="show durable messages in a thread")
    t.add_argument("thread_id")
    t.set_defaults(func=cmd_thread)

    rc = sub.add_parser("reconcile", help="refresh all semantic/runtime bindings")
    rc.add_argument("--new-epoch", action="store_true", help="rotate runtime epoch before reconciliation")
    rc.set_defaults(func=cmd_reconcile)

    d = sub.add_parser("demo", help="run a deterministic mock Claude/Codex round-trip")
    d.add_argument("--demo-dir", default="run/demo")
    d.set_defaults(func=cmd_demo)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
