from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
from pathlib import PurePosixPath
from typing import Any, Callable, Mapping

from eml_wake.canonical import canonical_bytes, loads_strict
from eml_wake.errors import WakeError
from eml_wake.filesystem import _verify_no_reparse, publish_no_replace

from .canonical import object_content_digest, profile_digest
from .errors import RelationContractError
from .events import RelationContractEvent, validate_event_object_binding


EXPECTED_TOP_LEVEL = {
    "objects",
    "events",
    "indexes",
    "duplicates",
    "quarantine",
    "adoptions",
}
EXPECTED_ADOPTION_LAYOUT = {"pending", "adopted", "quarantine"}
PRODUCTION_MARKERS = {
    ".git",
    "PRODUCTION_REGISTRY_ROOT.md",
    "registry-manifest.json",
    "private",
}
VERSIONED_IDS = {
    "relation": ("relation_id", "version"),
    "contract": ("contract_id", "version"),
    "commitment": ("commitment_id", "version"),
    "activation_policy": ("policy_id", "policy_version"),
    "party_evidence": ("party_ref", "state_head_ref", "state_view_digest"),
}
SINGLE_IDS = {
    "grant_authority": "grant_authority_evidence_id",
    "representation_grant": "representation_grant_id",
    "acceptance": "acceptance_id",
    "authority_candidate": "candidate_id",
    "authority_evaluation": "receipt_digest",
}
DIGEST_FIELDS = {"authority_evaluation": "receipt_digest"}
SCHEMA_BY_KIND = {
    "relation": "arcp/relation-version/0.1",
    "contract": "arcp/contract-version/0.1",
    "commitment": "arcp/commitment/0.1",
    "activation_policy": "arcp/activation-policy/0.1",
    "party_evidence": "arcp/party-evidence-pin/0.1",
    "grant_authority": "arcp/grant-authority-evidence/0.1",
    "representation_grant": "arcp/representation-grant/0.1",
    "acceptance": "arcp/party-acceptance/0.1",
    "authority_candidate": "arcp/authority-candidate/0.1",
    "authority_evaluation": "arcp/authority-evaluation-receipt/0.1",
}


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _hash_value(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bundle_digest(value: Mapping[str, Any]) -> str:
    return profile_digest({key: item for key, item in value.items() if key != "bundle_digest"})


def _convert(error: WakeError) -> RelationContractError:
    return RelationContractError(error.code, error.message)


def _publish(path: Path, value: dict[str, Any]) -> None:
    try:
        publish_no_replace(path, value)
    except WakeError as error:
        raise _convert(error) from error


def _read_canonical(path: Path) -> dict[str, Any]:
    try:
        data = path.read_bytes()
        value = loads_strict(data)
    except (OSError, WakeError) as error:
        raise RelationContractError("stored_record_unreadable", str(path)) from error
    if not isinstance(value, dict):
        raise RelationContractError("stored_record_invalid", str(path))
    if data != canonical_bytes(value):
        raise RelationContractError("stored_record_not_canonical", str(path))
    return value


@dataclass(frozen=True)
class StoredObjectResult:
    status: str
    kind: str
    identity_tuple: tuple[Any, ...]
    content_digest: str
    bundle_path: str
    index_path: str


@dataclass(frozen=True)
class AppendEventResult:
    status: str
    event_id: str
    event_digest: str
    bundle_path: str
    index_path: str


@dataclass(frozen=True)
class StoreVerification:
    status: str
    valid: bool
    error_codes: tuple[str, ...]
    object_count: int
    event_count: int
    head_digest: str | None


@dataclass(frozen=True)
class RepairResult:
    created_indexes: int


class RelationContractStore:
    def __init__(
        self,
        root: str | Path,
        *,
        fault_injector: Callable[[str], None] | None = None,
    ):
        self.root = Path(root)
        self.fault_injector = fault_injector
        self._prepare_root()
        self.objects_dir = self.root / "objects"
        self.events_dir = self.root / "events"
        self.object_index_dir = self.root / "indexes" / "object-digests"
        self.event_index_dir = self.root / "indexes" / "event-digests"
        self.duplicates_dir = self.root / "duplicates"
        self.quarantine_dir = self.root / "quarantine"
        self.adoptions_dir = self.root / "adoptions"
        self.adoptions_pending_dir = self.adoptions_dir / "pending"
        self.adoptions_adopted_dir = self.adoptions_dir / "adopted"
        self.adoptions_quarantine_dir = self.adoptions_dir / "quarantine"
        for directory in (
            self.objects_dir,
            self.events_dir,
            self.object_index_dir,
            self.event_index_dir,
            self.duplicates_dir,
            self.quarantine_dir,
            self.adoptions_dir,
            self.adoptions_pending_dir,
            self.adoptions_adopted_dir,
            self.adoptions_quarantine_dir,
        ):
            directory.mkdir(parents=True, exist_ok=True)
        try:
            _verify_no_reparse(self.root, self.root)
            for directory in (
                self.objects_dir,
                self.events_dir,
                self.object_index_dir,
                self.event_index_dir,
                self.duplicates_dir,
                self.quarantine_dir,
                self.adoptions_dir,
                self.adoptions_pending_dir,
                self.adoptions_adopted_dir,
                self.adoptions_quarantine_dir,
            ):
                _verify_no_reparse(self.root, directory)
        except (OSError, ValueError, WakeError) as error:
            raise RelationContractError("storage_root_refused", str(self.root)) from error

    def _prepare_root(self) -> None:
        if self.root.exists():
            if not self.root.is_dir() or self.root.is_symlink():
                raise RelationContractError("storage_root_refused", str(self.root))
            existing = {item.name for item in self.root.iterdir()}
            if existing & PRODUCTION_MARKERS or existing - EXPECTED_TOP_LEVEL:
                raise RelationContractError("storage_root_refused", str(self.root))
        else:
            self.root.mkdir(parents=True, exist_ok=True)
            if not self.root.is_dir() or self.root.is_symlink():
                raise RelationContractError("storage_root_refused", str(self.root))
        if ".git" in self.root.parts:
            raise RelationContractError("storage_root_refused", str(self.root))

    def _fault(self, stage: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector(stage)

    def _safe_store_path(self, path: Path, *, must_exist: bool) -> Path:
        root = Path(os.path.abspath(self.root))
        target = Path(os.path.abspath(path))
        try:
            target.relative_to(root)
            resolved_root = root.resolve(strict=True)
            resolved_target = target.resolve(strict=must_exist)
            resolved_target.relative_to(resolved_root)
            checked = target if target.exists() else target.parent
            while checked != root and not checked.exists():
                checked = checked.parent
            _verify_no_reparse(root, checked)
        except (OSError, ValueError, WakeError) as error:
            raise RelationContractError("storage_path_refused", str(path)) from error
        if must_exist and not target.is_file():
            raise RelationContractError("storage_path_refused", str(path))
        return target

    def _read_store_record(self, path: Path) -> dict[str, Any]:
        return _read_canonical(self._safe_store_path(path, must_exist=True))

    def _publish_store_record(self, path: Path, value: dict[str, Any]) -> None:
        target = self._safe_store_path(path, must_exist=False)
        _publish(target, value)

    def _bundle_path_from_index(
        self, value: Mapping[str, Any], *, expected_kind: str
    ) -> Path:
        raw = value.get("bundle_path")
        if not isinstance(raw, str) or not raw or "\\" in raw:
            raise RelationContractError("storage_path_refused", str(raw))
        pure = PurePosixPath(raw)
        parts = pure.parts
        if (
            pure.is_absolute()
            or pure.as_posix() != raw
            or len(parts) != 3
            or parts[0] != "objects"
            or parts[1] != expected_kind
            or parts[2] in {"", ".", ".."}
            or any(part in {"", ".", ".."} for part in parts)
        ):
            raise RelationContractError("storage_path_refused", raw)
        return self._safe_store_path(
            self.root.joinpath(*parts), must_exist=True
        )

    def _identity_tuple(self, kind: str, value: Mapping[str, Any]) -> tuple[Any, ...]:
        if kind in VERSIONED_IDS:
            fields = VERSIONED_IDS[kind]
        elif kind in SINGLE_IDS:
            fields = (SINGLE_IDS[kind],)
        else:
            raise RelationContractError("object_kind_invalid", kind)
        try:
            identity = tuple(value[field] for field in fields)
        except KeyError as error:
            raise RelationContractError("object_identity_invalid", kind) from error
        if any(item is None or isinstance(item, (dict, list)) for item in identity):
            raise RelationContractError("object_identity_invalid", kind)
        return (kind, *identity)

    def _object_digest(self, kind: str, value: Mapping[str, Any]) -> str:
        field = DIGEST_FIELDS.get(kind, "content_digest")
        digest = value.get(field)
        if not isinstance(digest, str) or digest != object_content_digest(dict(value), field):
            raise RelationContractError("content_digest_mismatch", kind)
        return digest

    def _validate_object(self, kind: str, value: Any) -> tuple[tuple[Any, ...], str]:
        if not isinstance(value, dict) or value.get("schema") != SCHEMA_BY_KIND.get(kind):
            raise RelationContractError("object_kind_invalid", kind)
        identity = self._identity_tuple(kind, value)
        return identity, self._object_digest(kind, value)

    def _object_path(self, kind: str, identity: tuple[Any, ...]) -> Path:
        return self.objects_dir / kind / f"{_hash_value(list(identity))}.json"

    def _event_path(self, event_id: str) -> Path:
        return self.events_dir / f"{_hash_text(event_id)}.json"

    def _object_index_path(self, digest: str) -> Path:
        return self.object_index_dir / f"{_hash_text(digest)}.json"

    def _event_index_path(self, digest: str) -> Path:
        return self.event_index_dir / f"{_hash_text(digest)}.json"

    def _duplicate_path(self, event: RelationContractEvent) -> Path:
        identity = f"{event.event_id}\x00{event.event_digest}"
        return self.duplicates_dir / f"{_hash_text(identity)}.json"

    def _quarantine(self, code: str, record: dict[str, Any]) -> None:
        value = {"schema": "arcp/relation-contract-quarantine/0.1", "code": code, **record}
        path = self.quarantine_dir / f"{_hash_value(value)}.json"
        try:
            self._publish_store_record(path, value)
        except RelationContractError as error:
            if (
                error.code != "immutable_file_exists"
                or self._read_store_record(path) != value
            ):
                raise

    def _object_bundle(
        self,
        kind: str,
        identity: tuple[Any, ...],
        digest: str,
        value: dict[str, Any],
    ) -> dict[str, Any]:
        bundle = {
            "schema": "arcp/relation-contract-object-bundle/0.1",
            "kind": kind,
            "identity_tuple": list(identity),
            "content_digest": digest,
            "canonical_object": deepcopy(value),
            "bundle_digest": "",
        }
        bundle["bundle_digest"] = _bundle_digest(bundle)
        return bundle

    def _event_bundle(self, event: RelationContractEvent) -> dict[str, Any]:
        bundle = {
            "schema": "arcp/relation-contract-event-bundle/0.1",
            "event_id": event.event_id,
            "event_digest": event.event_digest,
            "canonical_event": event.to_dict(),
            "bundle_digest": "",
        }
        bundle["bundle_digest"] = _bundle_digest(bundle)
        return bundle

    def _object_index(self, kind: str, digest: str, path: Path) -> dict[str, Any]:
        return {
            "schema": "arcp/relation-contract-object-index/0.1",
            "kind": kind,
            "content_digest": digest,
            "bundle_path": path.relative_to(self.root).as_posix(),
        }

    def _event_index(self, event: RelationContractEvent, path: Path) -> dict[str, Any]:
        return {
            "schema": "arcp/relation-contract-event-index/0.1",
            "event_id": event.event_id,
            "event_digest": event.event_digest,
            "bundle_path": path.relative_to(self.root).as_posix(),
        }

    def _duplicate_evidence(
        self, event: RelationContractEvent, event_path: Path
    ) -> dict[str, Any]:
        value = {
            "schema": "arcp/relation-contract-duplicate-delivery/0.1",
            "event_id": event.event_id,
            "event_digest": event.event_digest,
            "event_bundle_path": event_path.relative_to(self.root).as_posix(),
            "duplicate_evidence_digest": "",
        }
        value["duplicate_evidence_digest"] = profile_digest(
            {
                key: item
                for key, item in value.items()
                if key != "duplicate_evidence_digest"
            }
        )
        return value

    def _read_duplicate_evidence(self, path: Path) -> dict[str, Any]:
        value = self._read_store_record(path)
        if (
            set(value)
            != {
                "schema",
                "event_id",
                "event_digest",
                "event_bundle_path",
                "duplicate_evidence_digest",
            }
            or value["schema"]
            != "arcp/relation-contract-duplicate-delivery/0.1"
        ):
            raise RelationContractError("duplicate_evidence_invalid", str(path))
        expected_digest = profile_digest(
            {
                key: item
                for key, item in value.items()
                if key != "duplicate_evidence_digest"
            }
        )
        expected_name = _hash_text(
            f"{value['event_id']}\x00{value['event_digest']}"
        )
        expected_bundle = f"events/{_hash_text(str(value['event_id']))}.json"
        if (
            value["duplicate_evidence_digest"] != expected_digest
            or path.name != f"{expected_name}.json"
            or value["event_bundle_path"] != expected_bundle
        ):
            raise RelationContractError("duplicate_evidence_invalid", str(path))
        return value

    def _record_duplicate(
        self, event: RelationContractEvent, event_path: Path
    ) -> None:
        expected = self._duplicate_evidence(event, event_path)
        path = self._duplicate_path(event)
        if path.exists():
            if self._read_duplicate_evidence(path) != expected:
                raise RelationContractError("duplicate_evidence_invalid", event.event_id)
            return
        try:
            self._publish_store_record(path, expected)
        except RelationContractError as error:
            if (
                error.code != "immutable_file_exists"
                or self._read_duplicate_evidence(path) != expected
            ):
                raise RelationContractError(
                    "duplicate_evidence_invalid", event.event_id
                ) from error

    def _publish_index(self, path: Path, value: dict[str, Any], code: str) -> None:
        if path.exists():
            if self._read_store_record(path) != value:
                raise RelationContractError(code, str(path))
            return
        try:
            self._publish_store_record(path, value)
        except RelationContractError as error:
            if (
                error.code != "immutable_file_exists"
                or self._read_store_record(path) != value
            ):
                raise RelationContractError(code, str(path)) from error

    def put_object(self, kind: str, value: dict[str, Any]) -> StoredObjectResult:
        identity, digest = self._validate_object(kind, value)
        bundle = self._object_bundle(kind, identity, digest, value)
        path = self._object_path(kind, identity)
        status = "created"
        if path.exists():
            existing = self._read_object_bundle(path)
            if (
                existing["content_digest"] == digest
                and existing["canonical_object"] == value
            ):
                status = "existing"
            else:
                self._quarantine(
                    "object_identity_collision",
                    {
                        "identity_tuple": list(identity),
                        "existing_content_digest": existing["content_digest"],
                        "submitted_content_digest": digest,
                        "submitted_object": deepcopy(value),
                    },
                )
                raise RelationContractError("object_identity_collision", str(identity))
        else:
            try:
                self._publish_store_record(path, bundle)
            except RelationContractError as error:
                if error.code != "immutable_file_exists":
                    raise
                existing = self._read_object_bundle(path)
                if (
                    existing["content_digest"] == digest
                    and existing["canonical_object"] == value
                ):
                    status = "existing"
                else:
                    self._quarantine(
                        "object_identity_collision",
                        {
                            "identity_tuple": list(identity),
                            "existing_content_digest": existing["content_digest"],
                            "submitted_content_digest": digest,
                            "submitted_object": deepcopy(value),
                        },
                    )
                    raise RelationContractError(
                        "object_identity_collision", str(identity)
                    ) from error
        index_path = self._object_index_path(digest)
        if status == "created":
            self._fault("after_object_bundle")
        self._publish_index(
            index_path,
            self._object_index(kind, digest, path),
            "object_index_invalid",
        )
        return StoredObjectResult(
            status, kind, identity, digest, str(path), str(index_path)
        )

    def append_event(self, event: RelationContractEvent) -> AppendEventResult:
        if not isinstance(event, RelationContractEvent):
            raise RelationContractError("event_type_invalid", "append")
        event_object = self.get_object(event.object_digest)
        validate_event_object_binding(event, event_object)
        for parent in event.causal_parents:
            parent_path = self._event_path(parent)
            if not parent_path.is_file():
                raise RelationContractError("contract_parent_missing", parent)
            try:
                parent_bundle = self._read_event_bundle(parent_path)
            except RelationContractError as error:
                raise RelationContractError("event_parent_invalid", parent) from error
            if parent_bundle["event_id"] != parent:
                raise RelationContractError("event_parent_invalid", parent)
        bundle = self._event_bundle(event)
        path = self._event_path(event.event_id)
        status = "created"
        if path.exists():
            existing = self._read_event_bundle(path)
            if existing["event_digest"] == event.event_digest and existing[
                "canonical_event"
            ] == event.to_dict():
                status = "existing"
            else:
                self._quarantine(
                    "event_id_collision",
                    {
                        "event_id": event.event_id,
                        "existing_event_digest": existing["event_digest"],
                        "submitted_event_digest": event.event_digest,
                        "submitted_event": event.to_dict(),
                    },
                )
                raise RelationContractError("event_id_collision", event.event_id)
        else:
            try:
                self._publish_store_record(path, bundle)
            except RelationContractError as error:
                if error.code != "immutable_file_exists":
                    raise
                existing = self._read_event_bundle(path)
                if existing["event_digest"] == event.event_digest and existing[
                    "canonical_event"
                ] == event.to_dict():
                    status = "existing"
                else:
                    self._quarantine(
                        "event_id_collision",
                        {
                            "event_id": event.event_id,
                            "existing_event_digest": existing["event_digest"],
                            "submitted_event_digest": event.event_digest,
                            "submitted_event": event.to_dict(),
                        },
                    )
                    raise RelationContractError(
                        "event_id_collision", event.event_id
                    ) from error
        if status == "existing":
            self._record_duplicate(event, path)
        index_path = self._event_index_path(event.event_digest)
        if status == "created":
            self._fault("after_event_bundle")
        self._publish_index(
            index_path,
            self._event_index(event, path),
            "event_index_invalid",
        )
        return AppendEventResult(
            status, event.event_id, event.event_digest, str(path), str(index_path)
        )

    def _read_object_bundle(self, path: Path) -> dict[str, Any]:
        value = self._read_store_record(path)
        if (
            set(value)
            != {
                "schema",
                "kind",
                "identity_tuple",
                "content_digest",
                "canonical_object",
                "bundle_digest",
            }
            or value["schema"] != "arcp/relation-contract-object-bundle/0.1"
            or value["bundle_digest"] != _bundle_digest(value)
        ):
            raise RelationContractError("object_bundle_invalid", str(path))
        identity, digest = self._validate_object(
            value["kind"], value["canonical_object"]
        )
        if list(identity) != value["identity_tuple"] or digest != value["content_digest"]:
            raise RelationContractError("object_bundle_invalid", str(path))
        if path.name != f"{_hash_value(list(identity))}.json":
            raise RelationContractError("object_bundle_filename_mismatch", str(path))
        return value

    def _read_event_bundle(self, path: Path) -> dict[str, Any]:
        value = self._read_store_record(path)
        if (
            set(value)
            != {"schema", "event_id", "event_digest", "canonical_event", "bundle_digest"}
            or value["schema"] != "arcp/relation-contract-event-bundle/0.1"
            or value["bundle_digest"] != _bundle_digest(value)
        ):
            raise RelationContractError("event_bundle_invalid", str(path))
        event = RelationContractEvent.from_dict(value["canonical_event"])
        if event.event_id != value["event_id"] or event.event_digest != value[
            "event_digest"
        ]:
            raise RelationContractError("event_bundle_invalid", str(path))
        if path.name != f"{_hash_text(event.event_id)}.json":
            raise RelationContractError("event_bundle_filename_mismatch", str(path))
        return value

    def _object_bundle_paths(self):
        return sorted(self.objects_dir.glob("*/*.json"))

    def _event_bundle_paths(self):
        return sorted(self.events_dir.glob("*.json"))

    def objects_by_digest(self) -> dict[str, dict[str, Any]]:
        result = {}
        for path in self._object_bundle_paths():
            bundle = self._read_object_bundle(path)
            result[bundle["content_digest"]] = deepcopy(bundle["canonical_object"])
        return dict(sorted(result.items()))

    def get_object(self, content_digest: str) -> dict[str, Any]:
        index_path = self._object_index_path(content_digest)
        if index_path.is_file():
            index = self._read_store_record(index_path)
            if (
                index.get("schema") != "arcp/relation-contract-object-index/0.1"
                or index.get("content_digest") != content_digest
                or index.get("kind") not in set(VERSIONED_IDS) | set(SINGLE_IDS)
            ):
                raise RelationContractError("object_index_invalid", content_digest)
            path = self._bundle_path_from_index(
                index, expected_kind=str(index["kind"])
            )
            bundle = self._read_object_bundle(path)
            if (
                bundle["content_digest"] != content_digest
                or bundle["kind"] != index["kind"]
                or path != Path(os.path.abspath(self._object_path(
                    bundle["kind"], tuple(bundle["identity_tuple"])
                )))
            ):
                raise RelationContractError("object_index_invalid", content_digest)
            return deepcopy(bundle["canonical_object"])
        objects = self.objects_by_digest()
        if content_digest not in objects:
            raise RelationContractError("object_not_found", content_digest)
        return deepcopy(objects[content_digest])

    def events(self) -> tuple[RelationContractEvent, ...]:
        events = [
            RelationContractEvent.from_dict(
                self._read_event_bundle(path)["canonical_event"]
            )
            for path in self._event_bundle_paths()
        ]
        return tuple(sorted(events, key=lambda item: item.event_digest))

    def head_digest(self) -> str | None:
        events = self.events()
        if not events:
            return None
        parent_ids = {parent for event in events for parent in event.causal_parents}
        heads = sorted(
            event.event_digest for event in events if event.event_id not in parent_ids
        )
        return profile_digest({"event_head_digests": heads, "kind": "relation-contract-head"})

    def _index_errors(self) -> tuple[list[str], int]:
        errors: list[str] = []
        missing = 0
        object_bundles = {}
        event_bundles = {}
        for path in self._object_bundle_paths():
            bundle = self._read_object_bundle(path)
            object_bundles[bundle["content_digest"]] = (path, bundle)
            expected = self._object_index(
                bundle["kind"], bundle["content_digest"], path
            )
            index_path = self._object_index_path(bundle["content_digest"])
            if not index_path.is_file():
                missing += 1
            else:
                try:
                    if self._read_store_record(index_path) != expected:
                        errors.append("object_index_invalid")
                except RelationContractError:
                    errors.append("object_index_invalid")
        for path in self._event_bundle_paths():
            bundle = self._read_event_bundle(path)
            event = RelationContractEvent.from_dict(bundle["canonical_event"])
            event_bundles[event.event_digest] = (path, event)
            expected = self._event_index(event, path)
            index_path = self._event_index_path(event.event_digest)
            if not index_path.is_file():
                missing += 1
            else:
                try:
                    if self._read_store_record(index_path) != expected:
                        errors.append("event_index_invalid")
                except RelationContractError:
                    errors.append("event_index_invalid")
        for path in sorted(self.object_index_dir.glob("*.json")):
            try:
                index = self._read_store_record(path)
                if index.get("content_digest") not in object_bundles:
                    errors.append("object_index_invalid")
            except RelationContractError:
                errors.append("object_index_invalid")
        for path in sorted(self.event_index_dir.glob("*.json")):
            try:
                index = self._read_store_record(path)
                if index.get("event_digest") not in event_bundles:
                    errors.append("event_index_invalid")
            except RelationContractError:
                errors.append("event_index_invalid")
        return errors, missing

    def _duplicate_errors(
        self, events_by_id: Mapping[str, RelationContractEvent]
    ) -> list[str]:
        errors: list[str] = []
        entries = sorted(self.duplicates_dir.iterdir())
        if any(not path.is_file() or path.suffix != ".json" for path in entries):
            errors.append("duplicate_evidence_invalid")
        for path in (item for item in entries if item.is_file() and item.suffix == ".json"):
            try:
                value = self._read_duplicate_evidence(path)
                event = events_by_id.get(str(value["event_id"]))
                if event is None or event.event_digest != value["event_digest"]:
                    errors.append("duplicate_evidence_invalid")
            except RelationContractError:
                errors.append("duplicate_evidence_invalid")
        return errors

    def verify(self, expected_head: str | None = None) -> StoreVerification:
        errors: list[str] = []
        existing = {item.name for item in self.root.iterdir()}
        if existing - EXPECTED_TOP_LEVEL:
            errors.append("storage_layout_invalid")
        adoption_entries = {item.name for item in self.adoptions_dir.iterdir()}
        if adoption_entries != EXPECTED_ADOPTION_LAYOUT or any(
            not (self.adoptions_dir / name).is_dir()
            for name in EXPECTED_ADOPTION_LAYOUT
        ):
            errors.append("storage_layout_invalid")
        object_count = 0
        event_count = 0
        missing_indexes = 0
        try:
            objects = self.objects_by_digest()
            object_count = len(objects)
            events = self.events()
            event_count = len(events)
            by_id = {event.event_id: event for event in events}
            for event in events:
                if event.object_digest not in objects:
                    errors.append("event_object_missing")
                else:
                    try:
                        validate_event_object_binding(
                            event, objects[event.object_digest]
                        )
                    except RelationContractError as error:
                        errors.append(error.code)
                if any(parent not in by_id for parent in event.causal_parents):
                    errors.append("event_parent_missing")
            errors.extend(self._duplicate_errors(by_id))
            index_errors, missing_indexes = self._index_errors()
            errors.extend(index_errors)
        except RelationContractError as error:
            errors.append(error.code)
        head = None
        try:
            head = self.head_digest()
        except RelationContractError as error:
            errors.append(error.code)
        if expected_head is not None and expected_head != head:
            errors.append("external_head_mismatch")
        error_codes = tuple(sorted(set(errors)))
        if error_codes:
            status = "invalid"
        elif missing_indexes:
            status = "repairable_index_gap"
        elif not object_count and not event_count:
            status = "empty"
        elif expected_head is not None:
            status = "checkpoint_verified"
        else:
            status = "internally_consistent"
        return StoreVerification(
            status,
            status == "checkpoint_verified",
            error_codes,
            object_count,
            event_count,
            head,
        )

    def repair_indexes(self) -> RepairResult:
        verification = self.verify()
        if verification.status == "invalid":
            raise RelationContractError(
                "store_invalid", ",".join(verification.error_codes)
            )
        created = 0
        for path in self._object_bundle_paths():
            bundle = self._read_object_bundle(path)
            index_path = self._object_index_path(bundle["content_digest"])
            if not index_path.exists():
                self._publish_store_record(
                    index_path,
                    self._object_index(bundle["kind"], bundle["content_digest"], path),
                )
                created += 1
        for path in self._event_bundle_paths():
            bundle = self._read_event_bundle(path)
            event = RelationContractEvent.from_dict(bundle["canonical_event"])
            index_path = self._event_index_path(event.event_digest)
            if not index_path.exists():
                self._publish_store_record(index_path, self._event_index(event, path))
                created += 1
        return RepairResult(created)
