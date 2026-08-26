from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import jsonschema
from eml_wake.canonical import canonical_bytes, loads_strict
from eml_wake.errors import WakeError

from .contracts import load_relation_contract
from .errors import RelationContractError
from .events import RelationContractEvent
from .models_authority import (
    AuthorityCandidate,
    AuthorityEvaluationReceipt,
    CommitmentRecord,
    GrantAuthorityEvidence,
    PartyAcceptance,
    RepresentationGrant,
)
from .models_common import PartyEvidencePin
from .models_relation import RelationVersion
from .policy import ActivationPolicy
from .projector import explain_subject, rebuild_projection
from .store import RelationContractStore


KIND_CONTRACTS = {
    "activation_policy": "activation-policy-v1.schema.json",
    "party_evidence": "party-evidence-pin-v1.schema.json",
    "relation": "relation-version-v1.schema.json",
    "contract": "contract-version-v1.schema.json",
    "grant_authority": "grant-authority-evidence-v1.schema.json",
    "representation_grant": "representation-grant-v1.schema.json",
    "acceptance": "party-acceptance-v1.schema.json",
    "commitment": "commitment-v1.schema.json",
    "authority_candidate": "authority-candidate-v1.schema.json",
    "authority_evaluation": "authority-evaluation-receipt-v1.schema.json",
    "event": "relation-contract-event-v1.schema.json",
}
KIND_BY_SCHEMA = {
    "arcp/activation-policy/0.1": "activation_policy",
    "arcp/party-evidence-pin/0.1": "party_evidence",
    "arcp/relation-version/0.1": "relation",
    "arcp/contract-version/0.1": "contract",
    "arcp/grant-authority-evidence/0.1": "grant_authority",
    "arcp/representation-grant/0.1": "representation_grant",
    "arcp/party-acceptance/0.1": "acceptance",
    "arcp/commitment/0.1": "commitment",
    "arcp/authority-candidate/0.1": "authority_candidate",
    "arcp/authority-evaluation-receipt/0.1": "authority_evaluation",
}
SEMANTIC_VALIDATORS: dict[str, Callable[[dict[str, Any]], Any]] = {
    "activation_policy": ActivationPolicy.from_dict,
    "party_evidence": PartyEvidencePin.from_dict,
    "relation": RelationVersion.from_dict,
    "grant_authority": GrantAuthorityEvidence.from_dict,
    "representation_grant": RepresentationGrant.from_dict,
    "acceptance": PartyAcceptance.from_dict,
    "commitment": CommitmentRecord.from_dict,
    "authority_candidate": AuthorityCandidate.from_dict,
    "authority_evaluation": AuthorityEvaluationReceipt.from_dict,
    "event": RelationContractEvent.from_dict,
}
INPUT_ERROR_CODES = {"bom_not_allowed", "invalid_json", "invalid_utf8"}
PROFILE_REJECTION_CODES = {"duplicate_key", "unsupported_number"}


def _emit(value: dict[str, Any]) -> None:
    print(canonical_bytes(value).decode("utf-8"))


def _read_object(path: str | Path) -> dict[str, Any]:
    try:
        raw = Path(path).read_bytes()
    except OSError as error:
        raise RelationContractError("input_unreadable", "input") from error
    try:
        value = loads_strict(raw)
    except WakeError:
        raise
    if not isinstance(value, dict):
        raise RelationContractError("input_invalid_json", "object required")
    return value


def _validate_value(kind: str, value: dict[str, Any]) -> None:
    schema_name = KIND_CONTRACTS.get(kind)
    if schema_name is None:
        raise RelationContractError("object_kind_invalid", kind)
    try:
        jsonschema.validate(value, load_relation_contract(schema_name))
    except jsonschema.ValidationError as error:
        raise RelationContractError("schema_invalid", kind) from error
    validator = SEMANTIC_VALIDATORS.get(kind)
    if validator is not None:
        validator(value)


def _infer_kind(value: dict[str, Any]) -> str:
    kind = KIND_BY_SCHEMA.get(value.get("schema"))
    if kind is None:
        raise RelationContractError("object_kind_invalid", str(value.get("schema")))
    return kind


def _run(handler, args) -> int:
    try:
        return int(handler(args))
    except WakeError as error:
        code = 1 if error.code in INPUT_ERROR_CODES else 2
        if error.code not in INPUT_ERROR_CODES | PROFILE_REJECTION_CODES:
            code = 2
        _emit(
            {
                "reason_codes": [error.code],
                "status": "error" if code == 1 else "rejected",
            }
        )
        return code
    except RelationContractError as error:
        code = 1 if error.code.startswith("input_") else 2
        if error.code == "store_not_projectable" and error.message in {
            "empty",
            "repairable_index_gap",
        }:
            code = 4
        _emit(
            {
                "reason_codes": [error.code],
                "status": (
                    "error"
                    if code == 1
                    else "indeterminate"
                    if code == 4
                    else "rejected"
                ),
            }
        )
        return code
    except OSError:
        _emit({"reason_codes": ["storage_unavailable"], "status": "error"})
        return 1


def cmd_validate(args) -> int:
    _validate_value(args.kind, _read_object(args.file))
    _emit({"reason_codes": [], "status": "valid"})
    return 0


def cmd_append(args) -> int:
    object_value = _read_object(args.object)
    kind = _infer_kind(object_value)
    _validate_value(kind, object_value)
    event = RelationContractEvent.from_dict(_read_object(args.event))
    store = RelationContractStore(args.root)
    object_result = store.put_object(kind, object_value)
    event_result = store.append_event(event)
    _emit(
        {
            "event_digest": event_result.event_digest,
            "event_id": event_result.event_id,
            "object_digest": object_result.content_digest,
            "status": (
                "existing"
                if object_result.status == event_result.status == "existing"
                else "created"
            ),
        }
    )
    return 0


def cmd_project(args) -> int:
    store = RelationContractStore(args.root)
    verification = store.verify()
    if verification.status == "empty":
        _emit(
            {
                "projection": None,
                "reason_codes": ["store_empty"],
                "status": "indeterminate",
            }
        )
        return 4
    projection = loads_strict(rebuild_projection(store))
    if projection["conflicts"]:
        _emit(
            {
                "projection": projection,
                "reason_codes": ["conflicted_heads"],
                "status": "conflicted",
            }
        )
        return 3
    if any(
        value["candidate_status"] == "indeterminate"
        for value in projection["authority_candidates"].values()
    ):
        _emit(
            {
                "projection": projection,
                "reason_codes": ["authority_candidate_indeterminate"],
                "status": "indeterminate",
            }
        )
        return 4
    _emit({"projection": projection, "reason_codes": [], "status": "projected"})
    return 0


def cmd_explain(args) -> int:
    explanation = explain_subject(RelationContractStore(args.root), args.subject_ref)
    _emit({"explanation": explanation, "reason_codes": [], "status": "explained"})
    return 0


def cmd_verify(args) -> int:
    result = RelationContractStore(args.root).verify(args.expected_head)
    value = {
        "error_codes": list(result.error_codes),
        "event_count": result.event_count,
        "head_digest": result.head_digest,
        "object_count": result.object_count,
        "status": result.status,
        "valid": result.valid,
    }
    _emit(value)
    if result.status == "invalid":
        return 2
    if result.status in {"empty", "repairable_index_gap"}:
        return 4
    return 0


def register_subcommands(subparsers) -> None:
    parser = subparsers.add_parser("relation-contract-validate")
    parser.add_argument("file")
    parser.add_argument("--kind", choices=sorted(KIND_CONTRACTS), required=True)
    parser.set_defaults(func=lambda args: _run(cmd_validate, args))

    parser = subparsers.add_parser("relation-contract-append")
    parser.add_argument("--root", required=True)
    parser.add_argument("--object", required=True)
    parser.add_argument("--event", required=True)
    parser.set_defaults(func=lambda args: _run(cmd_append, args))

    parser = subparsers.add_parser("relation-contract-project")
    parser.add_argument("--root", required=True)
    parser.set_defaults(func=lambda args: _run(cmd_project, args))

    parser = subparsers.add_parser("relation-contract-explain")
    parser.add_argument("--root", required=True)
    parser.add_argument("subject_ref")
    parser.set_defaults(func=lambda args: _run(cmd_explain, args))

    parser = subparsers.add_parser("relation-contract-verify")
    parser.add_argument("--root", required=True)
    parser.add_argument("--expected-head")
    parser.set_defaults(func=lambda args: _run(cmd_verify, args))
