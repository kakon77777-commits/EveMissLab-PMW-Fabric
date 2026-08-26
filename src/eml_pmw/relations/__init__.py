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
from .arcp_adapter import (
    AuthorityEvaluatorIndeterminate,
    AuthorityEvaluatorPort,
    AuthorityEvaluatorUnavailable,
    DeterministicAuthorityEvaluator,
    EvaluationDecision,
    OfflineEvaluatorGrant,
    evaluate_with_port,
)
from .federation_adapter import (
    AdoptionHistoryVerification,
    AdoptionResult,
    ExplicitRelationAdoptionReceipt,
    ImportedRelationObservation,
    adopt_relation_event,
    inspect_imported_relation_event,
    verify_adoption_history,
    wrap_relation_event,
)
from .portability import (
    ConformanceResult,
    PortabilityFinding,
    PortabilityReport,
    run_portable_conformance,
    scan_portable_profile,
)
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
    "AdoptionHistoryVerification",
    "AdoptionResult",
    "ActivationDecision",
    "ActivationInputs",
    "AuthorityCandidate",
    "AuthorityEvaluationReceipt",
    "AuthorityEvaluatorIndeterminate",
    "AuthorityEvaluatorPort",
    "AuthorityEvaluatorUnavailable",
    "AppendEventResult",
    "CommitmentRecord",
    "ConformanceResult",
    "ContractVersion",
    "DeterministicAuthorityEvaluator",
    "EvaluationDecision",
    "ExplicitRelationAdoptionReceipt",
    "ExitPath",
    "EVENT_KINDS",
    "EVENT_RULES",
    "GrantAuthorityEvidence",
    "NormalizedInstantEvidence",
    "OfflineEvaluatorGrant",
    "LifecycleProjection",
    "ImportedRelationObservation",
    "PartyEvidencePin",
    "PortabilityFinding",
    "PortabilityReport",
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
    "adopt_relation_event",
    "build_authority_candidate",
    "evaluate_activation",
    "evaluate_with_port",
    "explain_subject",
    "inspect_imported_relation_event",
    "object_content_digest",
    "profile_digest",
    "projection_digest",
    "ral_pin_sufficient",
    "reduce_events",
    "rebuild_projection",
    "receipt_is_current",
    "run_portable_conformance",
    "scan_portable_profile",
    "validate_grant_authority",
    "verify_adoption_history",
    "validate_portable_ref",
    "wrap_relation_event",
]
