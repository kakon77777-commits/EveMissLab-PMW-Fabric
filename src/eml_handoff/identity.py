from __future__ import annotations

from typing import Protocol

from .errors import HandoffError
from .models import HandoffConfig, HandoffEnvelope


class TargetBindingVerifier(Protocol):
    def verify_exact_instance(
        self,
        target_ref: str,
        receiver_instance_ref: str,
        binding_kind: str,
        evidence_ref: str,
    ) -> bool:
        raise NotImplementedError

    def verify_entity(
        self,
        target_ref: str,
        receiver_entity_ref: str,
        evidence_ref: str,
    ) -> bool:
        raise NotImplementedError


def authorize_claim(
    envelope: HandoffEnvelope,
    config: HandoffConfig,
    *,
    receiver_instance_ref: str | None,
    binding_kind: str,
    receiver_entity_ref: str | None,
    claim_authority_ref: str,
    evidence_ref: str | None,
    verifier: TargetBindingVerifier | None,
) -> None:
    if claim_authority_ref not in config.allowed_authority_refs:
        raise HandoffError("claim_authority_not_allowed", claim_authority_ref)
    if binding_kind not in {
        "codex_thread",
        "session_uuid",
        "provider_session",
        "unresolved",
    }:
        raise HandoffError("binding_kind_unsupported", binding_kind)
    if binding_kind == "unresolved" and receiver_instance_ref is not None:
        raise HandoffError(
            "unresolved_binding_has_instance", "receiver_instance_ref"
        )
    if binding_kind != "unresolved" and not receiver_instance_ref:
        raise HandoffError("receiver_instance_missing", binding_kind)

    if envelope.target_kind in {"shared_topic", "task"}:
        return
    if envelope.target_kind == "exact_instance":
        if verifier is None:
            raise HandoffError(
                "host_binding_verifier_unavailable",
                "exact instance claim requires host verification",
            )
        if not receiver_instance_ref or not evidence_ref:
            raise HandoffError(
                "host_binding_evidence_missing", "exact instance claim"
            )
        if not verifier.verify_exact_instance(
            envelope.target_ref,
            receiver_instance_ref,
            binding_kind,
            evidence_ref,
        ):
            raise HandoffError(
                "exact_instance_target_mismatch", envelope.target_ref
            )
        return
    if envelope.target_kind == "arcp_entity":
        if verifier is None:
            raise HandoffError(
                "entity_binding_verifier_unavailable",
                "entity claim requires ARCP/RAL verification",
            )
        if not receiver_entity_ref or not evidence_ref:
            raise HandoffError("entity_binding_evidence_missing", "entity claim")
        if not verifier.verify_entity(
            envelope.target_ref, receiver_entity_ref, evidence_ref
        ):
            raise HandoffError("entity_target_mismatch", envelope.target_ref)
        return
    raise HandoffError("target_kind_unsupported", envelope.target_kind)
