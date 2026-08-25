from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .errors import FederationError
from .models import FederatedEvent, FederationConfig


@dataclass(frozen=True)
class AuthorityVerification:
    status: str
    authority_ref: str | None
    action: str
    subject_ref: str
    evidence_ref: str | None

    def __post_init__(self) -> None:
        if self.status not in {"verified", "rejected", "unmeasured", "not_required"}:
            raise FederationError("authority_verification_status_invalid", self.status)
        if self.status == "verified" and (
            not isinstance(self.evidence_ref, str) or not self.evidence_ref
        ):
            raise FederationError("authority_evidence_missing", self.subject_ref)
        if self.status != "verified" and self.evidence_ref is not None:
            raise FederationError("authority_evidence_unexpected", self.subject_ref)


class AuthorityVerifier(Protocol):
    def verify(
        self, *, authority_ref: str | None, action: str, subject_ref: str
    ) -> AuthorityVerification: ...


def verify_event_authority(
    event: FederatedEvent,
    config: FederationConfig,
    verifier: AuthorityVerifier | None,
    *,
    action: str,
    subject_ref: str | None = None,
) -> AuthorityVerification:
    target = subject_ref or event.subject_ref
    if event.event_kind not in config.authority_required_event_kinds:
        return AuthorityVerification(
            "not_required", event.authority_ref, action, target, None
        )
    if verifier is None:
        return AuthorityVerification(
            "unmeasured", event.authority_ref, action, target, None
        )
    result = verifier.verify(
        authority_ref=event.authority_ref,
        action=action,
        subject_ref=target,
    )
    if not isinstance(result, AuthorityVerification):
        raise FederationError("authority_verifier_result_invalid", target)
    if (
        result.authority_ref != event.authority_ref
        or result.action != action
        or result.subject_ref != target
    ):
        raise FederationError("authority_verification_scope_mismatch", target)
    return result
