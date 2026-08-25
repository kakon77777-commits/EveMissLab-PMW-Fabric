from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any

from .errors import RelationContractError
from .references import validate_portable_ref


INSTANT_FIELDS = {
    "instant_ref",
    "clock_profile_id",
    "normalized_unix_ns",
    "uncertainty_ns",
    "verification_status",
    "source_evidence_refs",
}
INTEGER_TEXT = re.compile(r"^(?:0|-?[1-9][0-9]*)$")
TEMPORAL_STATUSES = {"verified", "observed", "unmeasured", "rejected"}


@dataclass(frozen=True)
class NormalizedInstantEvidence:
    instant_ref: str
    clock_profile_id: str
    normalized_unix_ns: str
    uncertainty_ns: int
    verification_status: str
    source_evidence_refs: tuple[str, ...]

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NormalizedInstantEvidence":
        if not isinstance(value, dict) or set(value) != INSTANT_FIELDS:
            raise RelationContractError("normalized_instant_invalid", "fields")
        if (
            not isinstance(value["normalized_unix_ns"], str)
            or not INTEGER_TEXT.fullmatch(value["normalized_unix_ns"])
            or isinstance(value["uncertainty_ns"], bool)
            or not isinstance(value["uncertainty_ns"], int)
            or value["uncertainty_ns"] < 0
            or value["verification_status"] not in TEMPORAL_STATUSES
            or not isinstance(value["source_evidence_refs"], list)
            or len(value["source_evidence_refs"])
            != len(set(value["source_evidence_refs"]))
        ):
            raise RelationContractError("normalized_instant_invalid", "value")
        refs = tuple(
            validate_portable_ref(item, "source_evidence_refs")
            for item in value["source_evidence_refs"]
        )
        if value["verification_status"] in {"verified", "observed"} and not refs:
            raise RelationContractError("normalized_instant_invalid", "evidence")
        return cls(
            validate_portable_ref(value["instant_ref"], "instant_ref"),
            validate_portable_ref(value["clock_profile_id"], "clock_profile_id"),
            value["normalized_unix_ns"],
            value["uncertainty_ns"],
            value["verification_status"],
            refs,
        )

    @property
    def lower_ns(self) -> int:
        return int(self.normalized_unix_ns) - self.uncertainty_ns

    @property
    def upper_ns(self) -> int:
        return int(self.normalized_unix_ns) + self.uncertainty_ns

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["source_evidence_refs"] = list(self.source_evidence_refs)
        return value


def compare_instants(
    left: NormalizedInstantEvidence, right: NormalizedInstantEvidence
) -> str:
    if left.verification_status not in {"verified", "observed"} or (
        right.verification_status not in {"verified", "observed"}
    ):
        raise RelationContractError(
            "temporal_evidence_insufficient", "comparison requires measured evidence"
        )
    if left.clock_profile_id != right.clock_profile_id:
        raise RelationContractError("clock_profile_mismatch", "comparison")
    if left.upper_ns < right.lower_ns:
        return "before"
    if right.upper_ns < left.lower_ns:
        return "after"
    if left.lower_ns == right.lower_ns and left.upper_ns == right.upper_ns:
        return "equal"
    return "overlap"
