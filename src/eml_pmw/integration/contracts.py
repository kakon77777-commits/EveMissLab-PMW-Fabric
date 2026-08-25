from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from importlib.resources import files
import json
from pathlib import Path
from typing import Any

from .errors import IntegrationContractError


PACKAGE = "eml_pmw.contracts.mrmic_phase13"
LOCAL_PACKAGE = "eml_pmw.contracts"


@dataclass(frozen=True)
class ContractLockResult:
    valid: bool
    source_commit: str
    digests: dict[str, str]
    reason_codes: tuple[str, ...]


def _safe_name(name: str) -> str:
    if not isinstance(name, str) or not name or Path(name).name != name:
        raise IntegrationContractError("contract_name_invalid", str(name))
    return name


def _root(root=None):
    return root if root is not None else files(PACKAGE)


def _load_json_item(item, *, code: str) -> dict[str, Any]:
    try:
        value = json.loads(item.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise IntegrationContractError(code, str(getattr(item, "name", item))) from error
    if not isinstance(value, dict):
        raise IntegrationContractError(code, str(getattr(item, "name", item)))
    return value


def load_contract(name: str) -> dict[str, Any]:
    return _load_json_item(
        _root().joinpath(_safe_name(name)), code="upstream_contract_invalid"
    )


def load_local_contract(name: str) -> dict[str, Any]:
    item = files(LOCAL_PACKAGE).joinpath(_safe_name(name))
    return _load_json_item(item, code="local_contract_invalid")


def verify_contract_lock(root=None) -> ContractLockResult:
    base = _root(root)
    reasons: list[str] = []
    actual: dict[str, str] = {}
    try:
        lock = _load_json_item(
            base.joinpath("lock.json"), code="contract_lock_invalid"
        )
        source_commit = str(lock["source"]["commit"])
        records = lock["files"]
    except (IntegrationContractError, KeyError, TypeError) as error:
        return ContractLockResult(
            False,
            "",
            {},
            (getattr(error, "code", "contract_lock_invalid"),),
        )
    if not isinstance(records, list):
        return ContractLockResult(False, source_commit, {}, ("contract_lock_invalid",))
    for record in records:
        try:
            name = _safe_name(record["name"])
            expected = record["sha256"]
            item = base.joinpath(name)
        except (IntegrationContractError, KeyError, TypeError):
            reasons.append("contract_lock_invalid")
            continue
        if not item.is_file():
            reasons.append("contract_file_missing")
            continue
        digest = sha256(item.read_bytes()).hexdigest()
        actual[name] = digest
        if digest != expected:
            reasons.append("contract_digest_mismatch")
    return ContractLockResult(
        valid=not reasons,
        source_commit=source_commit,
        digests=actual,
        reason_codes=tuple(sorted(set(reasons))),
    )
