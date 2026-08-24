from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

from .errors import WakeError


CANONICALIZATION_VERSION = "eml-wake-json-nfc-codepoint-v1"
_DOMAIN = b"EML-WAKE-CANONICAL\0" + CANONICALIZATION_VERSION.encode("ascii") + b"\0"


def _unsupported_number(_: str) -> Any:
    raise WakeError("unsupported_number", "floating-point and non-finite numbers are not allowed")


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise WakeError("duplicate_key", f"duplicate JSON object key: {key}")
        result[key] = value
    return result


def loads_strict(data: bytes) -> object:
    if data.startswith(b"\xef\xbb\xbf"):
        raise WakeError("bom_not_allowed", "UTF-8 BOM is not allowed")
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise WakeError("invalid_utf8", "input is not valid UTF-8") from exc
    try:
        return json.loads(
            text,
            object_pairs_hook=_pairs,
            parse_float=_unsupported_number,
            parse_constant=_unsupported_number,
        )
    except WakeError:
        raise
    except json.JSONDecodeError as exc:
        raise WakeError("invalid_json", f"invalid JSON at line {exc.lineno} column {exc.colno}") from exc


def _normalize(value: object) -> object:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for raw_key, item in value.items():
            if not isinstance(raw_key, str):
                raise WakeError("non_string_key", "JSON object keys must be strings")
            key = unicodedata.normalize("NFC", raw_key)
            if key in result:
                raise WakeError("normalized_key_collision", f"NFC-normalized key collision: {key}")
            result[key] = _normalize(item)
        return result
    raise WakeError("unsupported_type", f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    normalized = _normalize(value)
    try:
        text = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise WakeError("canonicalization_failed", str(exc)) from exc
    return text.encode("utf-8")


def digest_ref(value: object) -> str:
    digest = hashlib.sha256(_DOMAIN + canonical_bytes(value)).hexdigest()
    return f"sha256:{CANONICALIZATION_VERSION}:{digest}"
