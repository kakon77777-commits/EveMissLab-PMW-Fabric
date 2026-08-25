from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Any

from eml_wake.canonical import canonical_bytes, loads_strict
from eml_wake.errors import WakeError
from eml_wake.filesystem import _verify_no_reparse

from .authority import AuthorityVerification
from .causal import validate_graph
from .errors import FederationError
from .importer import import_event
from .inventory import FederationInventory, build_inventory, diff_inventories
from .models import FederatedEvent, FederationConfig, RealmRef, ReplicaRef, REQUIRED_NONCLAIMS
from .reconcile import reconcile_event, resolve_conflict
from .store import FederationStore, event_key


INPUT_CODES = {
    "input_unreadable",
    "input_invalid_json",
    "input_duplicate_key",
    "input_not_utf8",
}


def _emit(value: dict[str, Any]) -> None:
    print(canonical_bytes(value).decode("utf-8"))


def _read_bytes(path: str | Path) -> bytes:
    try:
        return Path(path).read_bytes()
    except OSError as error:
        raise FederationError("input_unreadable", str(path)) from error


def _read_object(path: str | Path) -> dict[str, Any]:
    data = _read_bytes(path)
    try:
        value = loads_strict(data)
    except WakeError as error:
        code = {
            "duplicate_key": "input_duplicate_key",
            "invalid_utf8": "input_not_utf8",
        }.get(error.code, "input_invalid_json")
        raise FederationError(code, str(path)) from error
    if not isinstance(value, dict):
        raise FederationError("input_invalid_json", str(path))
    return value


def _config(path: str | Path) -> FederationConfig:
    return FederationConfig.from_dict(_read_object(path))


def _store(args) -> FederationStore:
    return FederationStore(args.root, _config(args.config))


def _read_source_payload(path: str | Path, config: FederationConfig) -> bytes:
    requested = Path(os.path.abspath(path))
    try:
        target = requested.resolve(strict=True)
    except OSError as error:
        raise FederationError("input_unreadable", str(path)) from error
    matched = None
    attempts: list[str] = []
    for raw_root in config.allowed_source_roots:
        root_unresolved = Path(os.path.abspath(raw_root))
        try:
            requested.relative_to(root_unresolved)
            if config.strict_reparse_checks:
                _verify_no_reparse(root_unresolved, requested)
            root = root_unresolved.resolve(strict=True)
            target.relative_to(root)
        except WakeError as error:
            raise FederationError(error.code, error.message) from error
        except (OSError, ValueError) as error:
            attempts.append(
                f"raw={raw_root!r},unresolved={root_unresolved!s},"
                f"requested={requested!s},target={target!s},"
                f"error={type(error).__name__}:{error}"
            )
            continue
        matched = root
        break
    if matched is None or not target.is_file():
        raise FederationError(
            "payload_outside_allowlist",
            f"target={target}; attempts={' | '.join(attempts)}",
        )
    return _read_bytes(target)


class FileAuthorityVerifier:
    def __init__(self, value: dict[str, Any]):
        self.value = value

    def verify(self, *, authority_ref, action, subject_ref):
        expected = {
            "status",
            "authority_ref",
            "action",
            "subject_ref",
            "evidence_ref",
        }
        if set(self.value) != expected:
            raise FederationError("authority_verification_input_invalid", subject_ref)
        return AuthorityVerification(
            self.value["status"],
            self.value["authority_ref"],
            self.value["action"],
            self.value["subject_ref"],
            self.value["evidence_ref"],
        )


def _verifier(path: str | None):
    return None if path is None else FileAuthorityVerifier(_read_object(path))


def _run(handler, args) -> int:
    try:
        return int(handler(args))
    except FederationError as error:
        code = 1 if error.code in INPUT_CODES else 2
        _emit(
            {
                "reason_codes": [error.code],
                "status": "error" if code == 1 else "rejected",
            }
        )
        return code


def cmd_event_create(args) -> int:
    config = _config(args.config)
    store = FederationStore(args.root, config)
    payload = _read_source_payload(args.payload, config)
    source = Path(args.payload)
    media = {".json": "application/json", ".md": "text/markdown", ".txt": "text/plain"}.get(source.suffix.lower())
    if media is None:
        raise FederationError("payload_media_unsupported", source.suffix)
    realm = RealmRef.from_dict(_read_object(args.realm_ref))
    replica = ReplicaRef.from_dict(_read_object(args.replica_ref))
    payload_ref = f"payloads/{event_key(args.event_id)}{source.suffix.lower()}"
    event = FederatedEvent.from_dict(
        {
            "schema": "pmw-federated-event/v1",
            "event_id": args.event_id,
            "event_kind": args.kind,
            "subject_ref": args.subject_ref,
            "realm_ref": realm.__dict__ | {"evidence_refs": list(realm.evidence_refs)},
            "replica_ref": replica.__dict__ | {"evidence_refs": list(replica.evidence_refs)},
            "replica_seq": args.replica_seq,
            "causal_parents": list(args.parent),
            "claimed_actor_ref": args.claimed_actor_ref,
            "claimed_instance_ref": args.claimed_instance_ref,
            "authority_ref": args.authority_ref,
            "payload_ref": payload_ref,
            "payload_sha256": hashlib.sha256(payload).hexdigest().upper(),
            "payload_media_type": media,
            "fabric_payload_class": args.payload_class,
            "created_time_ref": args.created_time_ref,
            "temporal_evidence_status": "registered_anchor" if args.created_time_ref else "unavailable",
            "local_recorded_at": args.local_recorded_at,
            "correction_of": args.correction_of,
            "withdraws": args.withdraws,
            "not_claimed": sorted(REQUIRED_NONCLAIMS),
        }
    )
    result = store.submit(event, payload, delivery_id=args.delivery_id)
    _emit(
        {
            "event_digest": event.core_digest,
            "event_id": event.event_id,
            "fabric_payload_class": event.fabric_payload_class,
            "status": result.kind,
        }
    )
    return 0


def cmd_event_inventory(args) -> int:
    _emit(build_inventory(_store(args)).to_dict())
    return 0


def cmd_event_diff(args) -> int:
    local = FederationInventory.from_dict(_read_object(args.local))
    remote = FederationInventory.from_dict(_read_object(args.remote))
    result = diff_inventories(local, remote)
    changed = bool(
        result.digest_mismatches
        or result.missing_from_local
        or result.missing_from_remote
    )
    _emit(
        {
            "digest_mismatches": list(result.digest_mismatches),
            "missing_from_local": list(result.missing_from_local),
            "missing_from_remote": list(result.missing_from_remote),
            "status": "different" if changed else "equal",
        }
    )
    return 2 if result.digest_mismatches else 0


def cmd_event_import(args) -> int:
    result = import_event(
        _store(args),
        _read_bytes(args.event),
        _read_bytes(args.payload),
        _read_object(args.observer),
    )
    _emit(
        {
            "event_id": result.event_id,
            "missing_parent_ids": list(result.missing_parent_ids),
            "status": result.status,
        }
    )
    return 4 if result.status == "pending_dependencies" else 0


def cmd_event_reconcile(args) -> int:
    result = reconcile_event(
        _store(args), args.event_id, verifier=_verifier(args.authority_verification)
    )
    _emit(
        {
            "conflict_class": result.conflict_class,
            "conflict_id": result.conflict_id,
            "event_id": result.event_id,
            "reason_codes": list(result.reason_codes),
            "status": result.status,
        }
    )
    return {"adopted": 0, "rejected": 2, "conflict": 3, "parallel_branch": 3, "pending_dependencies": 4, "unmeasured": 4}[result.status]


def cmd_conflict_show(args) -> int:
    _emit(_store(args).get_conflict(args.conflict_id))
    return 0


def cmd_conflict_resolve(args) -> int:
    store = _store(args)
    event_bytes = _read_bytes(args.event)
    try:
        value = loads_strict(event_bytes)
    except WakeError as error:
        raise FederationError("input_invalid_json", args.event) from error
    if not isinstance(value, dict) or event_bytes != canonical_bytes(value):
        raise FederationError("event_not_canonical", args.event)
    event = FederatedEvent.from_dict(value)
    result = resolve_conflict(
        store,
        args.conflict_id,
        event,
        _read_bytes(args.payload),
        verifier=_verifier(args.authority_verification),
    )
    _emit(
        {
            "conflict_id": result.conflict_id,
            "resolution_event_id": result.resolution_event_id,
            "status": result.status,
        }
    )
    return 0


def cmd_sync_status(args) -> int:
    store = _store(args)
    graph = validate_graph(store.events())
    status = "ready"
    code = 0
    pending = 0
    if graph.code == "pending_dependencies":
        status, code, pending = "pending_dependencies", 4, len(graph.missing_parent_ids)
    elif not graph.valid:
        status, code = "invalid", 2
    _emit(
        {
            "conflicts": len(store.conflicts()),
            "events": len(store.events()),
            "pending_dependencies": pending,
            "resolutions": len(store.resolutions()),
            "status": status,
        }
    )
    return code


def register_subcommands(subparsers) -> None:
    common = lambda parser: (
        parser.add_argument("--root", required=True),
        parser.add_argument("--config", required=True),
    )
    parser = subparsers.add_parser("event-create")
    common(parser)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--kind", required=True)
    parser.add_argument("--subject-ref", required=True)
    parser.add_argument("--realm-ref", required=True)
    parser.add_argument("--replica-ref", required=True)
    parser.add_argument("--event-id", required=True)
    parser.add_argument("--replica-seq", required=True, type=int)
    parser.add_argument("--parent", action="append", default=[])
    parser.add_argument("--claimed-actor-ref")
    parser.add_argument("--claimed-instance-ref")
    parser.add_argument("--authority-ref")
    parser.add_argument("--payload-class", choices=["P0", "P1"], required=True)
    parser.add_argument("--created-time-ref")
    parser.add_argument("--local-recorded-at", required=True)
    parser.add_argument("--correction-of")
    parser.add_argument("--withdraws")
    parser.add_argument("--delivery-id", required=True)
    parser.set_defaults(func=lambda args: _run(cmd_event_create, args))

    parser = subparsers.add_parser("event-inventory")
    common(parser)
    parser.set_defaults(func=lambda args: _run(cmd_event_inventory, args))

    parser = subparsers.add_parser("event-diff")
    parser.add_argument("local")
    parser.add_argument("remote")
    parser.set_defaults(func=lambda args: _run(cmd_event_diff, args))

    parser = subparsers.add_parser("event-import")
    common(parser)
    parser.add_argument("--event", required=True)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--observer", required=True)
    parser.set_defaults(func=lambda args: _run(cmd_event_import, args))

    parser = subparsers.add_parser("event-reconcile")
    parser.add_argument("event_id")
    common(parser)
    parser.add_argument("--authority-verification")
    parser.set_defaults(func=lambda args: _run(cmd_event_reconcile, args))

    parser = subparsers.add_parser("conflict-show")
    parser.add_argument("conflict_id")
    common(parser)
    parser.set_defaults(func=lambda args: _run(cmd_conflict_show, args))

    parser = subparsers.add_parser("conflict-resolve")
    parser.add_argument("conflict_id")
    common(parser)
    parser.add_argument("--event", required=True)
    parser.add_argument("--payload", required=True)
    parser.add_argument("--authority-verification", required=True)
    parser.set_defaults(func=lambda args: _run(cmd_conflict_resolve, args))

    parser = subparsers.add_parser("sync-status")
    common(parser)
    parser.set_defaults(func=lambda args: _run(cmd_sync_status, args))
