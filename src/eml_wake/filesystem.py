from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import uuid

from .canonical import canonical_bytes, loads_strict
from .errors import WakeError
from .models import WakeConfig, WakeRequest


@dataclass(frozen=True)
class PayloadSnapshot:
    path: Path
    data: bytes
    sha256: str


def publish_bytes_no_replace(path: Path, data: bytes) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    staging = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    try:
        with staging.open("xb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(staging, path)
        except FileExistsError as exc:
            raise WakeError("immutable_file_exists", f"immutable file already exists: {path}") from exc
        except OSError as exc:
            raise WakeError(
                "immutable_publish_failed",
                f"no-replace publication failed: {exc}",
                details={"path": str(path), "errno": exc.errno},
            ) from exc
    finally:
        try:
            staging.unlink(missing_ok=True)
        except OSError:
            pass


def publish_no_replace(path: Path, value: dict) -> None:
    publish_bytes_no_replace(path, canonical_bytes(value))


def read_canonical_file(path: Path) -> dict:
    try:
        value = loads_strict(Path(path).read_bytes())
    except OSError as exc:
        raise WakeError("file_unreadable", f"cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WakeError("contract_type_invalid", f"canonical file must contain an object: {path}")
    return value


def _is_reparse(path: Path) -> bool:
    info = os.lstat(path)
    attrs = getattr(info, "st_file_attributes", 0)
    return bool(attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def _verify_no_reparse(root: Path, target: Path) -> None:
    if os.name != "nt":
        if root.is_symlink() or target.is_symlink():
            raise WakeError("payload_reparse_refused", "symlink payload path is refused")
        return
    current = root
    if _is_reparse(current):
        raise WakeError("payload_reparse_refused", f"allowlisted root is a reparse point: {current}")
    relative = target.relative_to(root)
    for part in relative.parts:
        current = current / part
        if _is_reparse(current):
            raise WakeError("payload_reparse_refused", f"payload path contains a reparse point: {current}")


def read_allowlisted_payload(request: WakeRequest, config: WakeConfig) -> PayloadSnapshot:
    requested = Path(request.payload_ref)
    try:
        target = requested.resolve(strict=True)
    except OSError as exc:
        raise WakeError("payload_unreadable", f"payload path is unavailable: {requested}") from exc

    matched_root: Path | None = None
    for raw_root in config.allowed_payload_roots:
        try:
            root = Path(raw_root).resolve(strict=True)
            target.relative_to(root)
        except (OSError, ValueError):
            continue
        matched_root = root
        break
    if matched_root is None:
        raise WakeError("payload_outside_allowlist", f"payload is outside configured roots: {target}")
    if config.strict_reparse_checks:
        _verify_no_reparse(matched_root, target)
    if not target.is_file():
        raise WakeError("payload_unreadable", f"payload is not a regular file: {target}")
    try:
        with target.open("rb") as handle:
            data = handle.read()
    except OSError as exc:
        raise WakeError("payload_unreadable", f"payload cannot be read: {target}") from exc
    digest = hashlib.sha256(data).hexdigest().upper()
    if digest != request.payload_sha256:
        raise WakeError(
            "payload_integrity_failed",
            "payload SHA-256 does not match request",
            details={"expected": request.payload_sha256, "actual": digest},
        )
    return PayloadSnapshot(path=target, data=data, sha256=digest)
