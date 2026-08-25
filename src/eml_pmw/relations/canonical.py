from __future__ import annotations

import hashlib
from typing import Any

from eml_wake.canonical import canonical_bytes


PROFILE_CANON = "arcp-relation-contract-json-nfc-codepoint-v1"
PROFILE_DOMAIN = b"ARCP-RELATION-CONTRACT\x00"


def profile_digest(value: dict[str, Any]) -> str:
    body = (
        PROFILE_DOMAIN
        + PROFILE_CANON.encode("ascii")
        + b"\x00"
        + canonical_bytes(value)
    )
    return f"sha256:{PROFILE_CANON}:" + hashlib.sha256(body).hexdigest()


def object_content_digest(
    value: dict[str, Any], digest_field: str = "content_digest"
) -> str:
    core = {key: item for key, item in value.items() if key != digest_field}
    return profile_digest(core)
