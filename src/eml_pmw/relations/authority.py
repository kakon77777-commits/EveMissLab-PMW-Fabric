from __future__ import annotations

from collections.abc import Mapping

from .errors import RelationContractError
from .models_authority import GrantAuthorityEvidence
from .models_common import PartyEvidencePin


def validate_grant_authority(
    root_ref: str,
    evidence_by_ref: Mapping[str, GrantAuthorityEvidence],
    forbidden_refs: set[str],
    forbidden_digests: set[str],
) -> tuple[str, ...]:
    visiting: set[str] = set()
    done: set[str] = set()

    def visit(ref: str) -> None:
        if ref in visiting:
            raise RelationContractError("representation_authority_circular", ref)
        if ref in done:
            return
        item = evidence_by_ref.get(ref)
        if item is None:
            raise RelationContractError("representation_authority_missing", ref)
        if (
            ref in forbidden_refs
            or item.authority_source_ref in forbidden_refs
            or item.content_digest in forbidden_digests
        ):
            raise RelationContractError("representation_authority_descendant", ref)
        visiting.add(ref)
        for dependency in item.dependency_refs:
            if dependency in forbidden_refs:
                raise RelationContractError(
                    "representation_authority_descendant", dependency
                )
            visit(dependency)
        visiting.remove(ref)
        done.add(ref)

    visit(root_ref)
    return tuple(sorted(done))


def ral_pin_sufficient(
    pin: PartyEvidencePin,
    *,
    current_ledger_head: str,
    current_view_digest: str,
) -> bool:
    return (
        pin.resolver_profile_id == "sedb-ral-public-view:v0.2"
        and pin.adapter_verification_status == "verified"
        and pin.party_status == "active"
        and pin.binding_status == "active"
        and pin.binding_ambiguity is False
        and pin.state_head_ref == current_ledger_head
        and pin.state_view_digest == current_view_digest
    )
