from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .canonical import object_content_digest
from .errors import RelationContractError
from .references import validate_portable_ref


POLICY_FIELDS = {
    "schema",
    "policy_id",
    "policy_version",
    "max_risk",
    "max_activation_duration_ms",
    "max_exit_notice_ms",
    "max_clock_uncertainty_ns",
    "allowed_evaluator_profiles",
    "allowed_clock_profiles",
    "require_revocable",
    "allow_redelegation",
    "allowed_residence_impact",
    "allowed_continuity_impact",
    "economic_terms_required",
    "content_digest",
}


def _unique_refs(value: Any, field: str) -> tuple[str, ...]:
    if (
        not isinstance(value, list)
        or not value
        or len(value) != len(set(value))
    ):
        raise RelationContractError("activation_policy_invalid", field)
    return tuple(validate_portable_ref(item, field) for item in value)


@dataclass(frozen=True)
class ActivationPolicy:
    schema: str
    policy_id: str
    policy_version: str
    max_risk: str
    max_activation_duration_ms: int
    max_exit_notice_ms: int
    max_clock_uncertainty_ns: int
    allowed_evaluator_profiles: tuple[str, ...]
    allowed_clock_profiles: tuple[str, ...]
    require_revocable: bool
    allow_redelegation: bool
    allowed_residence_impact: tuple[str, ...]
    allowed_continuity_impact: tuple[str, ...]
    economic_terms_required: None
    content_digest: str

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "ActivationPolicy":
        if not isinstance(value, dict) or set(value) != POLICY_FIELDS:
            raise RelationContractError("activation_policy_invalid", "fields")
        integers = (
            value["max_activation_duration_ms"],
            value["max_exit_notice_ms"],
            value["max_clock_uncertainty_ns"],
        )
        if (
            value["schema"] != "arcp/activation-policy/0.1"
            or not isinstance(value["policy_version"], str)
            or not value["policy_version"]
            or value["max_risk"] not in {"R0", "R1"}
            or any(isinstance(item, bool) or not isinstance(item, int) for item in integers)
            or value["max_activation_duration_ms"] <= 0
            or value["max_exit_notice_ms"] < 0
            or value["max_clock_uncertainty_ns"] < 0
            or value["require_revocable"] is not True
            or value["allow_redelegation"] is not False
            or value["allowed_residence_impact"] != ["none"]
            or value["allowed_continuity_impact"] != ["none"]
            or value["economic_terms_required"] is not None
        ):
            raise RelationContractError("activation_policy_invalid", "value")
        if value["content_digest"] != object_content_digest(value):
            raise RelationContractError("content_digest_mismatch", "activation policy")
        return cls(
            value["schema"],
            validate_portable_ref(value["policy_id"], "policy_id"),
            value["policy_version"],
            value["max_risk"],
            value["max_activation_duration_ms"],
            value["max_exit_notice_ms"],
            value["max_clock_uncertainty_ns"],
            _unique_refs(value["allowed_evaluator_profiles"], "allowed_evaluator_profiles"),
            _unique_refs(value["allowed_clock_profiles"], "allowed_clock_profiles"),
            True,
            False,
            ("none",),
            ("none",),
            None,
            value["content_digest"],
        )

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for field in (
            "allowed_evaluator_profiles",
            "allowed_clock_profiles",
            "allowed_residence_impact",
            "allowed_continuity_impact",
        ):
            value[field] = list(value[field])
        return value
