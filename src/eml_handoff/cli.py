from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
from typing import TextIO
import uuid

from .canonical import canonical_bytes, loads_strict
from .errors import HandoffError
from .filesystem import PayloadSnapshot, read_source_payload
from .identity import TargetBindingVerifier
from .models import HandoffConfig, HandoffEnvelope
from .store import HandoffStore, SubmissionResult, handoff_key
from .temporal import TemporalProvider, TemporalReceipt, temporal_provider


NOT_CLAIMED = [
    "sender_authorship_verified",
    "recipient_awake",
    "recipient_identity_continuity",
    "payload_understood",
    "authority_to_act_on_payload",
    "fast_transport_delivered",
]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _emit(value: object, stream: TextIO) -> None:
    stream.write(canonical_bytes(value).decode("utf-8") + "\n")
    stream.flush()


def _read_object(path: str | Path) -> dict:
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise HandoffError("input_unreadable", f"cannot read input: {path}") from error
    value = loads_strict(raw)
    if not isinstance(value, dict):
        raise HandoffError("contract_type_invalid", "input must contain an object")
    return value


def _load_config(path: str | Path) -> HandoffConfig:
    return HandoffConfig.from_dict(_read_object(path))


def _register_time(
    provider: TemporalProvider,
    label: str,
    meta: dict,
) -> TemporalReceipt:
    try:
        receipt = provider.register(label, meta)
    except Exception:
        return TemporalReceipt("unavailable", None, None, "temporal_provider_error")
    if receipt.status == "registered_anchor" and receipt.instant_id:
        return receipt
    return TemporalReceipt(
        "unavailable",
        None,
        None,
        receipt.error_code or "ctcl_unavailable",
    )


def _create(
    *,
    store: HandoffStore,
    config: HandoffConfig,
    source_path: str,
    claimed_sender_ref: str,
    claimed_sender_instance_ref: str,
    target_kind: str,
    target_ref: str,
    authority_ref: str,
    sensitivity: str,
    reply_to_handoff_id: str | None,
    temporal: TemporalProvider,
) -> tuple[SubmissionResult, HandoffEnvelope, TemporalReceipt]:
    if target_kind not in config.allowed_target_kinds:
        raise HandoffError("target_kind_not_allowed", target_kind)
    if authority_ref not in config.allowed_authority_refs:
        raise HandoffError("authority_not_allowed", authority_ref)
    if sensitivity not in {"P0", "P1"}:
        raise HandoffError("sensitivity_not_shareable", sensitivity)
    snapshot = read_source_payload(source_path, config)
    handoff_id = f"handoff:{uuid.uuid4()}"
    delivery_id = f"delivery:{uuid.uuid4()}"
    temporal_receipt = _register_time(
        temporal,
        "EML local durable handoff",
        {
            "handoff_id": handoff_id,
            "delivery_id": delivery_id,
            "target_kind": target_kind,
            "target_ref": target_ref,
            "payload_sha256": snapshot.sha256,
        },
    )
    envelope = HandoffEnvelope.from_dict(
        {
            "schema_version": "eml-handoff/envelope-0.1",
            "handoff_id": handoff_id,
            "delivery_id": delivery_id,
            "created_time_ref": temporal_receipt.instant_id,
            "temporal_evidence_status": temporal_receipt.status,
            "local_recorded_at": _now_iso(),
            "claimed_sender_ref": claimed_sender_ref,
            "claimed_sender_instance_ref": claimed_sender_instance_ref,
            "target_kind": target_kind,
            "target_ref": target_ref,
            "authority_ref": authority_ref,
            "payload_ref": f"payloads/{handoff_key(handoff_id)}{snapshot.extension}",
            "payload_media_type": snapshot.media_type,
            "payload_sha256": snapshot.sha256,
            "payload_bytes": snapshot.byte_count,
            "sensitivity": sensitivity,
            "reply_to_handoff_id": reply_to_handoff_id,
            "expires_at": None,
            "not_claimed": list(NOT_CLAIMED),
        }
    )
    result = store.submit(envelope, snapshot)
    return result, envelope, temporal_receipt


def _exit_for_status(status: str) -> int:
    if status == "acknowledged":
        return 0
    if status in {"pending", "claimed_incomplete", "materialized"}:
        return 3
    if status in {"host_binding_verifier_unavailable", "entity_binding_verifier_unavailable"}:
        return 4
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eml-handoff", description="Local durable cross-dialogue document mailbox"
    )
    parser.add_argument("--root", required=True)
    parser.add_argument("--config", required=True)
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create")
    create.add_argument("--payload", required=True)
    create.add_argument("--sender", required=True)
    create.add_argument("--sender-instance", required=True)
    create.add_argument("--target-kind", required=True)
    create.add_argument("--target-ref", required=True)
    create.add_argument("--authority", required=True)
    create.add_argument("--sensitivity", choices=["P0", "P1"], default="P1")

    listing = commands.add_parser("list")
    listing.add_argument("--target-kind", required=True)
    listing.add_argument("--target-ref", required=True)

    claim = commands.add_parser("claim")
    claim.add_argument("handoff_id")
    claim.add_argument("--receiver-instance", default=None)
    claim.add_argument(
        "--binding-kind",
        choices=["codex_thread", "session_uuid", "provider_session", "unresolved"],
        required=True,
    )
    claim.add_argument("--receiver-entity", default=None)
    claim.add_argument("--authority", required=True)
    claim.add_argument("--evidence", default=None)
    claim.add_argument("--observed-origin", default=None)

    materialize = commands.add_parser("materialize")
    materialize.add_argument("handoff_id")
    materialize.add_argument("--receiver-instance", default=None)

    ack = commands.add_parser("ack")
    ack.add_argument("handoff_id")
    ack.add_argument("--receiver-instance", default=None)
    ack.add_argument("--decision", choices=["ACK", "NO_ACTION", "ACTION", "ERROR"], required=True)
    ack.add_argument("--response-handoff", default=None)
    ack.add_argument("--evidence", action="append", required=True)

    reply = commands.add_parser("reply")
    reply.add_argument("handoff_id")
    reply.add_argument("--payload", required=True)
    reply.add_argument("--sender", required=True)
    reply.add_argument("--sender-instance", required=True)
    reply.add_argument("--target-kind", required=True)
    reply.add_argument("--target-ref", required=True)
    reply.add_argument("--authority", required=True)
    reply.add_argument("--receiver-instance", default=None)
    reply.add_argument(
        "--decision",
        choices=["ACK", "NO_ACTION", "ACTION", "ERROR"],
        default="ACK",
    )
    reply.add_argument("--evidence", action="append", required=True)
    reply.add_argument("--sensitivity", choices=["P0", "P1"], default="P1")

    status = commands.add_parser("status")
    status.add_argument("handoff_id")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    temporal: TemporalProvider | None = None,
    verifier: TargetBindingVerifier | None = None,
    stdout: TextIO | None = None,
) -> int:
    stream = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        config = _load_config(args.config)
        store = HandoffStore(args.root, config)
        time_source = temporal_provider(temporal, config.ctcl_endpoint)
        if args.command == "create":
            result, envelope, receipt = _create(
                store=store,
                config=config,
                source_path=args.payload,
                claimed_sender_ref=args.sender,
                claimed_sender_instance_ref=args.sender_instance,
                target_kind=args.target_kind,
                target_ref=args.target_ref,
                authority_ref=args.authority,
                sensitivity=args.sensitivity,
                reply_to_handoff_id=None,
                temporal=time_source,
            )
            _emit(
                {
                    "kind": result.kind,
                    "handoff_id": result.handoff_id,
                    "delivery_id": result.delivery_id,
                    "envelope_path": result.envelope_path,
                    "payload_path": result.payload_path,
                    "envelope": envelope.to_dict(),
                    "temporal_error_code": receipt.error_code,
                },
                stream,
            )
            return 0
        if args.command == "list":
            _emit(
                {
                    "target_kind": args.target_kind,
                    "target_ref": args.target_ref,
                    "handoff_ids": store.pending(args.target_kind, args.target_ref),
                },
                stream,
            )
            return 0
        if args.command == "claim":
            record = store.claim(
                args.handoff_id,
                receiver_instance_ref=args.receiver_instance,
                binding_kind=args.binding_kind,
                receiver_entity_ref=args.receiver_entity,
                claim_authority_ref=args.authority,
                evidence_ref=args.evidence,
                observed_origin=args.observed_origin,
                verifier=verifier,
            )
            _emit({"status": "claimed_incomplete", "record": record.to_dict()}, stream)
            return 0
        if args.command == "materialize":
            record = store.materialize(
                args.handoff_id, receiver_instance_ref=args.receiver_instance
            )
            envelope = store.get_envelope(args.handoff_id)
            _emit(
                {
                    "status": "materialized",
                    "record": record.to_dict(),
                    "payload_path": str(store.payload_path(envelope)),
                    "payload_bytes": envelope.payload_bytes,
                },
                stream,
            )
            return 0
        if args.command == "ack":
            temporal_receipt = _register_time(
                time_source,
                "EML local durable handoff receipt",
                {"handoff_id": args.handoff_id, "decision": args.decision},
            )
            record = store.commit_receipt(
                args.handoff_id,
                decision=args.decision,
                receiver_instance_ref=args.receiver_instance,
                response_handoff_id=args.response_handoff,
                evidence_refs=args.evidence,
                recorded_time_ref=temporal_receipt.instant_id,
            )
            _emit(
                {
                    "status": "acknowledged",
                    "record": record.to_dict(),
                    "temporal_error_code": temporal_receipt.error_code,
                },
                stream,
            )
            return 0
        if args.command == "reply":
            _, envelope, request_time = _create(
                store=store,
                config=config,
                source_path=args.payload,
                claimed_sender_ref=args.sender,
                claimed_sender_instance_ref=args.sender_instance,
                target_kind=args.target_kind,
                target_ref=args.target_ref,
                authority_ref=args.authority,
                sensitivity=args.sensitivity,
                reply_to_handoff_id=args.handoff_id,
                temporal=time_source,
            )
            receipt_time = _register_time(
                time_source,
                "EML local durable handoff receipt",
                {
                    "handoff_id": args.handoff_id,
                    "response_handoff_id": envelope.handoff_id,
                },
            )
            receipt = store.commit_receipt(
                args.handoff_id,
                decision=args.decision,
                receiver_instance_ref=args.receiver_instance,
                response_handoff_id=envelope.handoff_id,
                evidence_refs=args.evidence,
                recorded_time_ref=receipt_time.instant_id,
            )
            _emit(
                {
                    "status": "acknowledged",
                    "response": envelope.to_dict(),
                    "receipt": receipt.to_dict(),
                    "request_temporal_error_code": request_time.error_code,
                    "receipt_temporal_error_code": receipt_time.error_code,
                },
                stream,
            )
            return 0
        if args.command == "status":
            value = store.status(args.handoff_id)
            _emit(value, stream)
            return _exit_for_status(str(value["status"]))
        raise HandoffError("command_unknown", args.command)
    except HandoffError as error:
        _emit({"error": error.to_dict()}, stream)
        if error.code in {
            "input_unreadable",
            "invalid_json",
            "invalid_utf8",
            "bom_not_allowed",
            "payload_unreadable",
            "file_unreadable",
            "immutable_publish_failed",
        }:
            return 1
        if error.code in {
            "host_binding_verifier_unavailable",
            "entity_binding_verifier_unavailable",
        }:
            return 4
        return 2


def entrypoint() -> None:
    raise SystemExit(main())
