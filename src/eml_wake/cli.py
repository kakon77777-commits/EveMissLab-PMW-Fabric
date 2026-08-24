from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import sys
import threading
import time
from typing import TextIO
import uuid

from .canonical import canonical_bytes, loads_strict
from .claude import ClaudeCLIAdapter
from .errors import WakeError
from .filesystem import read_allowlisted_payload
from .models import WakeConfig, WakeRequest, WatchdogResult
from .provider import NotificationAdapter, NullNotifier, ProviderAdapter
from .store import WakeStore
from .temporal import CtclHttpTemporalProvider, TemporalProvider
from .watchdog import WakeWatchdog


def _emit(value: object, stream: TextIO) -> None:
    stream.write(canonical_bytes(value).decode("utf-8") + "\n")
    stream.flush()


def _read_object(path: str | Path) -> dict:
    try:
        raw = Path(path).read_bytes()
    except OSError as exc:
        raise WakeError("input_unreadable", f"cannot read input: {path}") from exc
    value = loads_strict(raw)
    if not isinstance(value, dict):
        raise WakeError("contract_type_invalid", "input must contain a JSON object")
    return value


def _load_config(path: str | Path) -> WakeConfig:
    return WakeConfig.from_dict(_read_object(path))


def _exit_for_status(status: str) -> int:
    if status == "acknowledged":
        return 0
    if status in {"pending", "claimed_incomplete"}:
        return 3
    if status.startswith("provider_") or status in {"ack_publish_failed"}:
        return 1
    return 2


def _watchdog(
    store: WakeStore,
    *,
    provider: ProviderAdapter | None,
    temporal: TemporalProvider | None,
    notifier: NotificationAdapter | None,
) -> WakeWatchdog:
    provider = provider or ClaudeCLIAdapter(binary=store.config.claude_binary)
    temporal = temporal or CtclHttpTemporalProvider(endpoint=store.config.ctcl_endpoint)
    notifier = notifier or NullNotifier()
    return WakeWatchdog(
        store,
        provider,
        notifier,
        f"watchdog:{uuid.uuid4()}",
        temporal=temporal,
    )


def watch_loop(
    watchdog: WakeWatchdog,
    *,
    poll_interval_ms: int,
    stop_event,
    sleeper=time.sleep,
) -> None:
    interval = max(poll_interval_ms / 1000.0, 0.001)
    while not stop_event.is_set():
        results = watchdog.run_once()
        if not results:
            sleeper(interval)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eml-wake", description="Durable external cross-dialogue watchdog")
    parser.add_argument("--root", required=True, help="durable wake root")
    parser.add_argument("--config", required=True, help="strict wake config JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    submit = sub.add_parser("submit", help="submit one strict wake request")
    submit.add_argument("request_file")

    create = sub.add_parser("create", help="create and submit a CTCL-anchored wake from one payload")
    create.add_argument("--payload", required=True)
    create.add_argument("--sender", required=True)
    create.add_argument("--authority", required=True)
    create.add_argument("--target-kind", default="generic_worker", choices=["generic_worker", "line"])
    create.add_argument("--target-ref", required=True)
    create.add_argument("--context-package", default=None)
    create.add_argument("--model", required=True)
    create.add_argument("--tools-policy", required=True)
    create.add_argument("--expires-seconds", type=int, default=600)
    create.add_argument("--max-budget-microusd", type=int, default=100000)
    create.add_argument("--timeout-ms", type=int, default=120000)

    sub.add_parser("run-once", help="process every currently pending wake once")

    watch = sub.add_parser("watch", help="poll and process pending wakes until interrupted")
    watch.add_argument("--poll-ms", type=int, default=None)

    status = sub.add_parser("status", help="show durable state for one wake")
    status.add_argument("wake_id")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    provider: ProviderAdapter | None = None,
    temporal: TemporalProvider | None = None,
    notifier: NotificationAdapter | None = None,
    stdout: TextIO | None = None,
) -> int:
    stream = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        config = _load_config(args.config)
        store = WakeStore(args.root, config)
        if args.command == "submit":
            request = WakeRequest.from_dict(_read_object(args.request_file))
            result = store.submit(request)
            _emit(
                {
                    "kind": result.kind,
                    "wake_id": result.wake_id,
                    "delivery_id": result.delivery_id,
                    "request_path": result.request_path,
                    "duplicate_path": result.duplicate_path,
                },
                stream,
            )
            return 0
        if args.command == "create":
            if args.tools_policy not in config.allowed_tools_by_policy:
                raise WakeError("tools_policy_not_found", f"tools policy not found: {args.tools_policy}")
            if args.model not in config.allowed_models:
                raise WakeError("model_not_allowed", f"model is not allowed: {args.model}")
            if args.target_kind not in config.allowed_target_kinds:
                raise WakeError("target_kind_not_allowed", f"target kind is not allowed: {args.target_kind}")
            if args.max_budget_microusd > config.maximum_budget_microusd:
                raise WakeError("budget_exceeds_policy", "request budget exceeds configured maximum")
            if args.timeout_ms > config.maximum_timeout_ms:
                raise WakeError("timeout_exceeds_policy", "request timeout exceeds configured maximum")
            if args.expires_seconds <= 0:
                raise WakeError("expiry_invalid", "expires-seconds must be positive")
            try:
                payload_path = Path(args.payload).resolve(strict=True)
                payload_sha256 = hashlib.sha256(payload_path.read_bytes()).hexdigest().upper()
            except OSError as exc:
                raise WakeError("input_unreadable", f"cannot read payload: {args.payload}") from exc
            wake_id = f"wake:{uuid.uuid4()}"
            delivery_id = f"delivery:{uuid.uuid4()}"
            temporal_provider = temporal or CtclHttpTemporalProvider(endpoint=config.ctcl_endpoint)
            receipt = temporal_provider.register(
                "EML wake request",
                {
                    "wake_id": wake_id,
                    "delivery_id": delivery_id,
                    "sender_claim": args.sender,
                    "target_kind": args.target_kind,
                    "target_ref": args.target_ref,
                    "payload_sha256": payload_sha256,
                },
            )
            if receipt.status != "registered_anchor" or not receipt.instant_id:
                raise WakeError(
                    "ctcl_request_anchor_unavailable",
                    "request CTCL registration did not produce a registered anchor",
                    details={"temporal_error_code": receipt.error_code},
                )
            now = datetime.now(timezone.utc)
            request = WakeRequest.from_dict(
                {
                    "schema_version": "eml-wake/request-0.1",
                    "wake_id": wake_id,
                    "delivery_id": delivery_id,
                    "created_time_ref": receipt.instant_id,
                    "expires_at": (now + timedelta(seconds=args.expires_seconds)).isoformat().replace(
                        "+00:00", "Z"
                    ),
                    "sender_claim": args.sender,
                    "target_kind": args.target_kind,
                    "target_ref": args.target_ref,
                    "spawn_allowed": True,
                    "authority_ref": args.authority,
                    "payload_ref": str(payload_path),
                    "payload_sha256": payload_sha256,
                    "context_package_ref": args.context_package,
                    "reply_policy": "durable_ack_only",
                    "provider": "claude",
                    "model": args.model,
                    "allowed_tools": list(config.allowed_tools_by_policy[args.tools_policy]),
                    "permission_mode": "dontAsk",
                    "max_budget_microusd": args.max_budget_microusd,
                    "timeout_ms": args.timeout_ms,
                    "requested_output_format": "json",
                    "not_claimed": ["resident continuity", "exact interactive instance"],
                }
            )
            read_allowlisted_payload(request, config)
            result = store.submit(request)
            _emit(
                {
                    "kind": result.kind,
                    "wake_id": result.wake_id,
                    "delivery_id": result.delivery_id,
                    "request_path": result.request_path,
                    "request": request.to_dict(),
                    "ctcl_receipt": receipt.receipt,
                },
                stream,
            )
            return 0
        if args.command == "status":
            result = store.status(args.wake_id)
            _emit(result, stream)
            return _exit_for_status(str(result["status"]))

        engine = _watchdog(store, provider=provider, temporal=temporal, notifier=notifier)
        if args.command == "run-once":
            results = engine.run_once()
            output = {
                "results": [
                    {"wake_id": item.wake_id, "status": item.status, "details": item.details}
                    for item in results
                ]
            }
            _emit(output, stream)
            codes = [_exit_for_status(item.status) for item in results]
            return max(codes, default=0)
        if args.command == "watch":
            stop = threading.Event()
            poll_ms = args.poll_ms if args.poll_ms is not None else config.poll_interval_ms
            try:
                watch_loop(engine, poll_interval_ms=poll_ms, stop_event=stop)
            except KeyboardInterrupt:
                stop.set()
            _emit({"status": "stopped"}, stream)
            return 0
        raise WakeError("command_unknown", f"unsupported command: {args.command}")
    except WakeError as exc:
        _emit({"error": exc.to_dict()}, stream)
        if exc.code in {
            "input_unreadable",
            "invalid_json",
            "invalid_utf8",
            "bom_not_allowed",
            "provider_binary_missing",
            "provider_start_failed",
            "provider_timeout",
            "provider_failed",
            "provider_busy",
            "ctcl_request_anchor_unavailable",
        }:
            return 1
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
