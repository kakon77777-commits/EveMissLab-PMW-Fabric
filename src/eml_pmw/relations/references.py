from __future__ import annotations

import re

from .errors import RelationContractError


WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:")
PYTHON_CLASS_PATH = re.compile(
    r"^(?:[A-Za-z_]\w*\.)+[A-Za-z_]\w*:[A-Za-z_]\w*$"
)


def validate_portable_ref(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or ":" not in value:
        raise RelationContractError("portable_ref_invalid", field)
    if (
        WINDOWS_DRIVE.match(value)
        or value.startswith(("\\\\", "/", "file://"))
        or PYTHON_CLASS_PATH.fullmatch(value)
    ):
        raise RelationContractError("portable_ref_invalid", field)
    if any(ord(character) < 0x20 for character in value):
        raise RelationContractError("portable_ref_invalid", field)
    return value
