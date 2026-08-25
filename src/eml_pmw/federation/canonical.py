from __future__ import annotations

import hashlib
from eml_wake.canonical import canonical_bytes

EVENT_CANON = "pmw-federated-event-json-nfc-codepoint-v1"
EVENT_DOMAIN = b"PMW-FEDERATED-EVENT\x00"


def event_digest(core: dict) -> str:
    body = EVENT_DOMAIN + EVENT_CANON.encode("ascii") + b"\x00" + canonical_bytes(core)
    return f"sha256:{EVENT_CANON}:" + hashlib.sha256(body).hexdigest()
