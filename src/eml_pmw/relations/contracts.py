from __future__ import annotations

from importlib.resources import files
import json
from pathlib import Path
from typing import Any

from .errors import RelationContractError


PACKAGE = "eml_pmw.contracts.relation_contract"


def load_relation_contract(name: str) -> dict[str, Any]:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise RelationContractError("contract_name_invalid", str(name))
    item = files(PACKAGE).joinpath(name)
    try:
        value = json.loads(item.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RelationContractError("contract_invalid", name) from error
    if not isinstance(value, dict):
        raise RelationContractError("contract_invalid", name)
    return value
