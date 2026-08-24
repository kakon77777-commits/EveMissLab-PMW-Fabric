from __future__ import annotations

from hashlib import sha256

from eml_wake.canonical import canonical_bytes as _wake_canonical_bytes
from eml_wake.canonical import loads_strict as _wake_loads_strict
from eml_wake.errors import WakeError

from .errors import HandoffError


CANONICALIZATION_VERSION = "eml-handoff-json-nfc-codepoint-v1"
_DOMAIN = b"EML-HANDOFF-CANONICAL\0" + CANONICALIZATION_VERSION.encode("ascii") + b"\0"


def _convert(error: WakeError) -> HandoffError:
    return HandoffError(error.code, error.message, details=error.details)


def canonical_bytes(value: object) -> bytes:
    try:
        return _wake_canonical_bytes(value)
    except WakeError as error:
        raise _convert(error) from error


def loads_strict(data: bytes) -> object:
    try:
        return _wake_loads_strict(data)
    except WakeError as error:
        raise _convert(error) from error


def digest_ref(value: object) -> str:
    digest = sha256(_DOMAIN + canonical_bytes(value)).hexdigest()
    return f"sha256:{CANONICALIZATION_VERSION}:{digest}"
