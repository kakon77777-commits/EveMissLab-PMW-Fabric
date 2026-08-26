"""Portable autonomous relation and contract profile."""

from .canonical import PROFILE_CANON, object_content_digest, profile_digest
from .errors import RelationContractError
from .policy import ActivationPolicy
from .references import validate_portable_ref
from .temporal import NormalizedInstantEvidence, compare_instants
from .models_common import PartyEvidencePin
from .models_authority import (
    AuthorityCandidate,
    AuthorityEvaluationReceipt,
    CommitmentRecord,
    GrantAuthorityEvidence,
    PartyAcceptance,
    RepresentationGrant,
)
from .authority import ral_pin_sufficient, validate_grant_authority
from .events import EVENT_KINDS, EVENT_RULES, RelationContractEvent
from .reducer import LifecycleProjection, reduce_events
from .projector import explain_subject, projection_digest, rebuild_projection
from .ral_adapter import RalPartyEvidenceAdapter
from .activation import (
    ActivationDecision,
    ActivationInputs,
    ReceiptCurrency,
    build_authority_candidate,
    evaluate_activation,
    receipt_is_current,
)
from .store import (
    AppendEventResult,
    RelationContractStore,
    RepairResult,
    StoredObjectResult,
    StoreVerification,
)
from .models_relation import (
    ContractVersion,
    ExitPath,
    RelationVersion,
    SurvivalClause,
    TerminationTerms,
)

__all__ = [
    "ActivationPolicy",
    "ActivationDecision",
    "ActivationInputs",
    "AuthorityCandidate",
    "AuthorityEvaluationReceipt",
    "AppendEventResult",
    "CommitmentRecord",
    "ContractVersion",
    "ExitPath",
    "EVENT_KINDS",
    "EVENT_RULES",
    "GrantAuthorityEvidence",
    "NormalizedInstantEvidence",
    "LifecycleProjection",
    "PartyEvidencePin",
    "PartyAcceptance",
    "PROFILE_CANON",
    "RelationContractError",
    "RelationContractEvent",
    "RelationContractStore",
    "RalPartyEvidenceAdapter",
    "RepairResult",
    "RelationVersion",
    "ReceiptCurrency",
    "RepresentationGrant",
    "SurvivalClause",
    "StoredObjectResult",
    "StoreVerification",
    "TerminationTerms",
    "compare_instants",
    "build_authority_candidate",
    "evaluate_activation",
    "explain_subject",
    "object_content_digest",
    "profile_digest",
    "projection_digest",
    "ral_pin_sufficient",
    "reduce_events",
    "rebuild_projection",
    "receipt_is_current",
    "validate_grant_authority",
    "validate_portable_ref",
]
