from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import os
from pathlib import Path

from eml_wake.errors import WakeError
from eml_wake.filesystem import _verify_no_reparse

from .contracts import MEDIA_BY_EXTENSION
from .errors import HandoffError
from .models import HandoffConfig


@dataclass(frozen=True)
class PayloadSnapshot:
    source_path: Path
    data: bytes
    sha256: str
    byte_count: int
    extension: str
    media_type: str


def _validate_text_document(data: bytes) -> None:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as error:
        raise HandoffError(
            "payload_binary_unsupported", "payload must be valid UTF-8 text"
        ) from error
    if any(ord(character) < 0x20 and character not in "\t\n\r" for character in text):
        raise HandoffError(
            "payload_binary_unsupported", "payload contains binary control bytes"
        )


def read_source_payload(path: str | Path, config: HandoffConfig) -> PayloadSnapshot:
    requested = Path(path)
    requested_unresolved = Path(os.path.abspath(requested))
    try:
        target = requested_unresolved.resolve(strict=True)
    except OSError as error:
        raise HandoffError("input_unreadable", f"cannot read payload: {requested}") from error

    matched_root: Path | None = None
    for raw_root in config.allowed_source_roots:
        root_unresolved = Path(os.path.abspath(raw_root))
        try:
            requested_unresolved.relative_to(root_unresolved)
            if config.strict_reparse_checks:
                _verify_no_reparse(root_unresolved, requested_unresolved)
            root = root_unresolved.resolve(strict=True)
            target.relative_to(root)
        except HandoffError:
            raise
        except WakeError as error:
            raise HandoffError(error.code, error.message, details=error.details) from error
        except (OSError, ValueError):
            continue
        matched_root = root
        break
    if matched_root is None:
        raise HandoffError(
            "payload_outside_allowlist", "payload is outside configured source roots"
        )
    if not target.is_file():
        raise HandoffError("input_unreadable", "payload is not a regular file")

    extension = target.suffix.lower()
    if extension not in config.allowed_payload_extensions:
        raise HandoffError("payload_extension_unsupported", extension or "<none>")
    media_type = MEDIA_BY_EXTENSION.get(extension)
    if media_type is None:
        raise HandoffError("payload_extension_unsupported", extension)
    try:
        data = target.read_bytes()
    except OSError as error:
        raise HandoffError("input_unreadable", "payload cannot be read") from error
    _validate_text_document(data)
    if len(data) > config.default_max_payload_bytes:
        raise HandoffError(
            "payload_too_large",
            "payload exceeds configured default",
            details={
                "payload_bytes": len(data),
                "maximum_bytes": config.default_max_payload_bytes,
            },
        )
    return PayloadSnapshot(
        source_path=target,
        data=data,
        sha256=sha256(data).hexdigest().upper(),
        byte_count=len(data),
        extension=extension,
        media_type=media_type,
    )
