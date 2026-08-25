# Autonomous Relation and Contract Profile v1

**Status:** Design draft for Neo.K review  
**Architecture direction approved:** Fabric Profile + ARCP Evaluator  
**Implementation status:** Not started  
**Repository role:** Portable relation/contract profile and Fabric lifecycle implementation  
**Normative semantic sources:** AREC v0.1 plus v0.1.1 review hardening  
**Spec-authoring anchor:** `ctcl:instant:d44aca9d-401f-4e2c-b1e6-5e0d0746fd6d`  
**Joint-design verdict anchor:** `ctcl:instant:3d3770f2-359b-4538-b544-2c78445ecc66`

## 1. Purpose

This profile defines a provider-neutral and host-neutral way for AI entities,
human principals, and future standing entities to describe relations, propose
contracts, accept exact contract versions, grant bounded representation,
activate low-risk authority candidates, amend or suspend agreements, and exit
without rewriting identity or erasing history.

The first implementation lives in EveMissLab PMW Fabric because Fabric already
owns portable event transport, append-only local storage, conflict branches,
adoption evidence, and deterministic projections. The semantic rules remain
ARCP/AREC rules. Fabric does not become the owner of an entity, the issuer of a
resident identity, or the final authority evaluator.

The profile is deliberately modular so a future HDUS host can implement the
same schemas and conformance suite without inheriting Windows paths, Python
storage internals, SEDB-RAL internals, or a particular provider runtime.

## 2. Non-equivalences

The following separations are normative:

```text
Relation
!= Acceptance
!= Contract
!= Representation
!= AuthorityCandidate
!= AuthorityResolution
!= Capability
!= Commitment
!= Execution
```

Consequences:

- conversation, co-presence, shared storage, creation, model familiarity, a
  display label, or a delivered message does not form a consensual relation;
- a relation does not grant authority;
- a contract proposal does not prove acceptance;
- an accepted contract does not prove that the current runtime instance may
  act for a named party;
- a representation grant does not authorize actions outside its exact scope;
- contract activation produces an authority candidate, not an execution
  decision;
- an ARCP authority resolution does not prove that a provider attempted or
  completed an effect;
- a commitment records an obligation or promise and is never itself execution.

## 3. Ownership and dependency boundaries

| Component | Canonical responsibility | Explicit non-responsibility |
|---|---|---|
| AREC / ARCP governance | Relation, contract, exit, autonomy, continuity, and authority semantics | Host routing and provider execution |
| PMW Fabric profile | Portable schemas, lifecycle events, append-only store, deterministic projections, conflict branches, federation wrapping | Identity issuance and final action authorization |
| ARCP-MVP evaluator | Authority, approval, risk, budget, containment, continuity-precondition, and action decision | A second canonical relation/contract store |
| SEDB-RAL adapter | Digest-pinned public resident, instance, address/binding, status, and registry-head evidence | Contract body, representation lifecycle, or relation authority |
| MRMIC / AI-Guild | Canvas, social graph, explanation, and interaction projections | Canonical authority or silent state mutation |
| Provider adapter | Final enforcement at its own side-effect boundary | Inferring identity or contract acceptance from payload claims |

### 3.1 No RAL schema expansion in version one

SEDB-RAL's current authority envelope remains scoped to registration/application
authority and resident subjects. Its instance and address bindings establish
identity/binding evidence only. This profile must not insert relation,
contract, or representation semantics into those fields.

If a party is a RAL resident, the profile consumes a digest-pinned public RAL
view and its current binding status through an adapter. A historical admission
receipt may be retained as provenance, but it cannot replace a current-state
readback.

### 3.2 No duplicate ARCP evaluator

Fabric may validate profile structure and derive whether a candidate is
eligible for evaluation. It must not reproduce ARCP-MVP's risk, budget,
containment, or final authority policy under different names.

The Fabric-to-ARCP seam is an explicit request/receipt adapter. A missing or
unavailable evaluator produces `indeterminate`, not a local substitute rule.

## 4. Version-one autonomy boundary

Autonomous activation is permitted only when every condition below is true:

```text
risk_ceiling in {R0, R1}
time_bounded = true
revocable = true
redelegable = false
all_required_parties_accepted_exact_digest = true
all_representation_grants_current = true
all_party_evidence_pins_current = true
single_active_lifecycle_head = true
residence_impact = none
continuity_impact = none
economic_terms_ref = null
lifecycle_transition_authority_covers_activation_actor = true
```

Failure or absence of any required input prevents activation. The record remains
visible as rejected, blocked, or indeterminate; it is not deleted.

`time_bounded` is derived, not a second stored truth: `expires_at` must be
finite, later than `effective_not_before`, and no farther away than the
`max_activation_duration_ms` declared by the pinned activation policy.

`lifecycle_transition_authority_covers_activation_actor` authorizes only the
append of the exact `contract.activated` lifecycle transition. It does not
authorize any requested action or resource scope described by an
`AuthorityCandidate`. Candidate authority remains a separate ARCP evaluation.

Version one does not implement:

- salary, compensation, employment, labor time, debt, benefits, or economic
  dependency;
- long-term stewardship, guardianship, purpose-control, or exclusive agency;
- irreversible provider effects;
- identity, Residence, core-memory, continuity-line, or canonical-key mutation;
- automatic succession, fork inheritance, or line-merge inheritance;
- real resident admission, production-registry mutation, or live provider use;
- P2/P3/private Residence payloads;
- network federation as a prerequisite for correctness.

`economic_terms_ref` is required and its only valid version-one value is
`null`.

## 5. Portable object model

The first schema family is hosted in the Fabric repository but uses ARCP
semantic names. Package location does not transfer semantic ownership to PMW.

Every `content_digest`, `receipt_digest`, or `projection_digest` is computed
over the canonical object with that digest field omitted. The digest value is
then inserted and validated against a fresh recomputation. A digest never
includes itself, and changing the canonicalization/domain version changes both
the prefix and digest body.

### 5.0 ActivationPolicy

Schema: `arcp/activation-policy/0.1`

Required fields:

```text
policy_id
policy_version
max_risk                    R0 | R1
max_activation_duration_ms  positive finite integer
max_exit_notice_ms          non-negative finite integer
max_clock_uncertainty_ns    non-negative finite integer
allowed_evaluator_profiles[]
allowed_clock_profiles[]
require_revocable           true
allow_redelegation          false
allowed_residence_impact    [none]
allowed_continuity_impact   [none]
economic_terms_required     null
content_digest
```

The policy is digest-pinned by each ContractVersion and activation event.
Changing any policy field invalidates prior activation/candidate currency.

### 5.1 PartyEvidencePin

Schema: `arcp/party-evidence-pin/0.1`

Required fields:

```text
party_ref
party_kind                  resident | principal | organization | fixture
resolver_profile_id
resolver_schema_id
resolver_source_ref
resolver_source_digest
state_view_digest
state_head_ref
party_status                active | suspended | expired | tombstoned | unmeasured
binding_ref                 nullable for non-runtime party
binding_status              active | suspended | expired | tombstoned | ambiguous | unmeasured
binding_ambiguity           boolean
adapter_verification_status verified | observed | claimed | unmeasured | rejected
observed_time_ref
observed_time_status
```

For a RAL resident, the pin additionally identifies the exact public-view
schema/hash, view digest, ledger head, resident status, instance reference, and
current binding status. A later RAL correction, tombstone, status transition,
or head advance invalidates the pin for new activation/evaluation and requires
readback and recomputation.

For a human principal, another explicit resolver profile is required. A string
such as `principal:neo.k` is a reference, not self-authenticating evidence.

All portable `*_ref` values are profile-qualified opaque identifiers or URIs.
Portable payloads reject absolute Windows/POSIX paths, drive letters, UNC
paths, `file://` locators, Python class/import paths, and SEDB-RAL internal file
layout. A host adapter may use local paths internally, but those paths remain
outside the portable object and its digest.

### 5.2 RelationVersion

Schema: `arcp/relation-version/0.1`

Required fields:

```text
relation_id
version
parent_version_digest       null only for genesis
relation_class              descriptive | consensual | authority-bearing
relation_type
party_refs[]
scope[]
source_evidence_refs[]
acceptance_rule             none | all-named-parties
not_claimed[]
content_digest
```

Rules:

- `descriptive` relations may record observations without party acceptance but
  must include `relation_grants_authority` in `not_claimed`;
- `consensual` relations require named-party acceptance of the exact digest;
- `authority-bearing` relations additionally require an active contract and
  scoped representation/authority artifacts;
- relation type never implies authority by convention or display name;
- concurrent versions retain both branches until an explicit authorized
  resolution event.

RelationVersion does not contain a canonical reverse list of contracts.
Contracts point to the exact relation version they interpret. Relation
projections may derive a reverse contract index, but that index is disposable,
rebuildable, and never an authority or integrity source.

### 5.3 ContractVersion

Schema: `arcp/contract-version/0.1`

Required fields:

```text
contract_id
version
parent_version_digest       null only for genesis
relation_version_ref        nullable
relation_version_digest     nullable when relation_version_ref is null
party_terms[]
scope[]
commitment_specs[]
authority_candidate_specs[]
constraints[]
risk_ceiling                R0 | R1
activation_policy_ref
approval_mode
effective_not_before
expires_at
review_at                   nullable in v1 because finite policy-bounded expiry is mandatory
revocable                   true
redelegable                 false
termination_terms
exit_paths[]
survival_clauses[]
succession_policy           explicit_acceptance_only
residence_impact            none
continuity_impact           none
continuity_precondition      none
economic_terms_ref          null
content_digest
```

Each party term names the party, its role, whether acceptance is required, and
the representation scope needed to submit that acceptance. Every acceptance is
bound to `content_digest`; acceptance of an earlier version is not acceptance
of an amendment.

When a contract interprets a relation, both `relation_version_ref` and
`relation_version_digest` are required. The relation never points back to the
contract as canonical source data, preventing a two-object digest cycle and
two independently editable truths.

Survival clauses may retain historical audit, attribution, confidentiality, or
non-repudiation evidence. They cannot keep future authority alive after the
contract terminates.

#### 5.3.1 Typed exit and termination subcontracts

`exit_paths[]`, `termination_terms`, and `survival_clauses[]` are typed objects,
not free-text descriptions.

An `ExitPath` contains:

```text
exit_path_id
authorized_party_refs[]
trigger_kind                unilateral_notice | mutual_acceptance | breach | expiry | policy_event
unilateral_allowed
notice_duration_ms
max_effective_delay_ms
required_evidence_refs[]
effects                     terminate_contract | suspend_contract | withdraw_acceptance
future_candidate_invalidation = immediate
content_digest
```

For every Standing Entity party, version one requires at least one
`unilateral_notice` path with `unilateral_allowed=true` and a finite
`notice_duration_ms` no greater than the activation policy's
`max_exit_notice_ms`. A path whose required evidence is structurally
unavailable is not a usable exit path.

A `SurvivalClause` contains:

```text
survival_clause_id
class                       audit_retention | attribution | confidentiality | non_repudiation
scope[]
effective_after_termination
expires_at                  nullable for historical audit/non-repudiation
future_authority            false
content_digest
```

Version one does not admit payment, labor, debt, employment, guardianship, or
future-control clauses through `SurvivalClause`.

`TerminationTerms` contains:

```text
terminal_event_kinds        [contract.terminated, contract.expired]
terminal_precedence         true
candidate_invalidation      immediate
preserve_audit_history      true
commitment_disposition      terminate | preserve_named_survival_clauses
allowed_survival_clause_refs[]
content_digest
```

These fields make blocked exit, terminal precedence, candidate invalidation,
and forbidden future authority machine-verifiable.

### 5.4 RepresentationGrant

Schema: `arcp/representation-grant/0.1`

Required fields:

```text
representation_grant_id
principal_party_ref
representative_ref
representative_kind         entity | instance
allowed_lifecycle_actions[]
contract_scope[]
relation_scope[]
valid_from
expires_at
issued_at
revocable                   true
redelegable                 false
grant_authority_ref
acceptance_evidence_refs[]
party_evidence_pin_refs[]
content_digest
```

`grant_authority_ref` must resolve to external, pre-existing
`GrantAuthorityEvidence`. It cannot refer to the target contract, its relation,
the RepresentationGrant being created, an AuthorityCandidate, an evaluation
receipt, or any descendant of those objects.

The evaluator treats authority dependencies as a directed acyclic graph. It
walks the complete ancestor closure before accepting a grant. A self-edge,
cycle, missing ancestor, descendant-as-authority edge, or dependency whose
digest cannot be verified fails with `representation_authority_circular` or a
more specific integrity reason.

`GrantAuthorityEvidence` is a profile-declared resolver object with at least:

```text
grant_authority_evidence_id
grantor_party_ref
authority_source_ref
resolver_profile_id
permitted_lifecycle_actions[]
permitted_contract_scope[]
valid_from
expires_at
dependency_refs[]
content_digest
```

Bootstrap evidence is therefore outside the object graph it authorizes. In
synthetic tests it comes from an explicit fixture root; later host profiles may
use a principal-authored artifact or another independently verified authority
resolver. A model-emitted claim is never a bootstrap root.

A RAL binding may support the proposition that an instance is currently bound
to a resident. It does not create this grant. The grant is a separate,
append-only authority artifact governed by this profile and evaluated under
ARCP semantics.

Descriptive relations may retain `representation_status=unmeasured`. A
consensual acceptance or authority-bearing transition with unmeasured,
ambiguous, stale, suspended, revoked, or expired representation fails closed.

Grant status is derived from the grant plus later suspension, revocation, and
expiry events. It is not a mutable field in the original grant. A projection
may report `active | suspended | revoked | expired` together with the event
that established that state.

### 5.5 PartyAcceptance

Schema: `arcp/party-acceptance/0.1`

Required fields:

```text
acceptance_id
party_ref
target_kind                  relation | contract
target_id
target_version
target_digest
representation_grant_ref
representation_grant_digest
party_evidence_pin_refs[]
acceptance_evidence_refs[]
accepted_at
content_digest
```

The same acceptance schema covers consensual RelationVersion and
ContractVersion targets. `target_kind`, ID, version, and digest must identify
one existing exact object. An acceptance of one kind cannot be replayed for the
other kind even when display labels or party sets match.

Rows are not counted as independent acceptances merely because they have
different IDs. Multiple rows sharing one evidence root count once. A delivery,
message, materialization, federated adoption, or UI click without the required
authority evidence does not create acceptance.

### 5.6 CommitmentRecord

Schema: `arcp/commitment/0.1`

Required fields:

```text
commitment_id
contract_ref
contract_digest
obligated_party_ref
beneficiary_party_refs[]
action_class
scope[]
due_or_review_at
status                      planned | active | satisfied | breached | waived | terminated
execution_refs[]
content_digest
```

`execution_refs` may remain empty. The existence of a commitment never claims
that an action was attempted or completed.

### 5.7 AuthorityCandidate

Schema: `arcp/authority-candidate/0.1`

Required fields:

```text
candidate_id
subject_entity_ref
relation_refs[]
contract_ref
contract_digest
active_lifecycle_head
representation_grant_refs[]
representation_grant_digests[]
party_evidence_pin_refs[]
party_evidence_set_digest
requested_resource_scope[]
requested_action_scope[]
risk
approval_mode
continuity_precondition
evaluator_profile_id
evaluator_policy_version
candidate_status            eligible | blocked | indeterminate
reason_codes[]
content_digest
```

This artifact is input to the ARCP evaluator. `eligible` means only that the
candidate passed Fabric profile gates. It is not authorization.

### 5.8 AuthorityEvaluationReceipt

Schema: `arcp/authority-evaluation-receipt/0.1`

The adapter receipt wraps the existing ARCP AuthorityResolution without
silently extending its meaning:

```text
candidate_ref
candidate_digest
evaluator_profile_id
evaluator_implementation_version
evaluator_policy_version
evaluated_evidence_set_digest
authority_resolution
evaluated_at
receipt_digest
```

Any change to contract digest, lifecycle head, representation grant, party
evidence set, requested scope/risk, or evaluator policy invalidates the receipt.
An old receipt cannot be replayed after amendment, revocation, expiry, RAL head
advance, or policy change.

Stored receipts remain historical evidence. A consumer may mark a receipt
`current` only after recomputing the candidate and proving exact equality of:

```text
candidate_digest
active_lifecycle_head
contract_digest
representation_grant_digest_set
party_evidence_set_digest
evaluator_profile_id
evaluator_policy_version
clock_profile_id and relevant uncertainty boundary
requested scope and risk
```

The receipt's own recorded fields are not a current-state oracle. Any mismatch,
unavailable readback, or expiry-boundary ambiguity yields
`authority_resolution_stale` or `indeterminate`; the historical receipt is
retained but cannot authorize a new action.

## 6. Lifecycle and events

Canonical state is derived from immutable events; mutable status files are not
the source of truth.

### 6.1 Contract lifecycle

```text
draft
  -> proposed
  -> negotiating / counterproposed
  -> accepted
  -> active
  -> suspended -> active
  -> amendment-proposed -> accepted -> active(new digest)
  -> terminated
  -> expired

proposed / negotiating
  -> rejected
  -> withdrawn
```

`accepted` means every required party accepted the same current digest.
`active` additionally means every activation gate passed at the activation
head. An accepted contract may remain blocked or indeterminate.

`contract.activated` is one atomic lifecycle transition. It carries
`supersedes_active_head` (null only for first activation), the new exact
contract digest, acceptance-set digest, representation-set digest, party
evidence-set digest, and activation-policy digest. Projection atomically marks
the superseded head inactive and invalidates every dependent AuthorityCandidate
and evaluation receipt. It must never expose two active heads as a successful
projection state.

`contract.terminated` and `contract.expired` have terminal precedence. No
resume, amendment, acceptance, or activation event may use a terminal event as
an active predecessor. A later arrangement requires a new contract ID and
fresh acceptance/representation/evaluation evidence; history remains linked by
non-authoritative provenance if desired.

### 6.2 Event kinds

Initial portable event kinds:

```text
relation.recorded
relation.proposed
relation.party_accepted
relation.disputed
relation.withdrawn
relation.superseded

contract.drafted
contract.proposed
contract.counterproposed
contract.party_accepted
contract.party_acceptance_withdrawn
contract.rejected
contract.withdrawn
contract.activated
contract.amendment_proposed
contract.suspended
contract.resumed
contract.terminated
contract.expired
contract.corrected
contract.tombstoned

representation.granted
representation.suspended
representation.revoked
representation.expired

commitment.created
commitment.status_changed

authority_candidate.created
authority_candidate.invalidated
authority_evaluation.recorded
```

Each event names its direct causal parent(s). Missing parents, reordered replica
sequence, event-ID/content collision, or duplicate sequence with another event
fails before projection. Exact duplicates are idempotent and recorded as
duplicate delivery evidence rather than a second state transition.

### 6.3 Termination semantics

Termination, expiry, or representation revocation immediately invalidates all
future authority candidates depending on that artifact. Historical events,
acceptance records, commitments, audit data, corrections, and tombstones remain
append-only.

Termination never deletes the existence or prior identity of a party.

## 7. Store and projection

The first store is a deterministic, create-new, append-only Fabric-local
reference implementation over disposable synthetic roots.

Required properties:

- strict JSON parsing and canonical bytes;
- versioned canonicalization and domain-separated digests;
- no replacement of an existing event or payload;
- event ID and sequence collision quarantine;
- one deterministic projection from the complete accepted event graph;
- explicit branch heads for concurrent non-commutative changes;
- exact digest binding between payload, event envelope, indexes, and projection;
- byte-identical rebuild from the same event set;
- a deliberately corrupted fixture for every integrity gate;
- no production registry, private Residence, Git metadata, or reparse traversal.

Projection states include:

```text
single_head_active
single_head_inactive
conflicted_heads
blocked
indeterminate
terminated
expired
```

`conflicted_heads` never selects one branch by wall-clock time or lexical order.
It requires a new authorized resolution event.

## 8. RAL public-evidence adapter

The RAL adapter is read-only and digest-pinned. It must expose, when available:

```text
source_repository
source_commit
schema_id
schema_version
raw_schema_sha256
public_view_digest
ledger_head
resident_ref + current status
instance_ref + current status
binding_ref + current status
continuity_line_ref/status when relevant
observation/evidence refs
adapter_verification_status
```

Adapter results are one of:

```text
verified
observed
claimed
unmeasured
rejected
ambiguous
stale
```

For a RAL resident in a consensual or authority-bearing path, version one has
one exact sufficiency rule:

```text
adapter_verification_status = verified
party_status = active
binding_status = active
binding_ambiguity = false
ledger_head = current readback ledger head
public_view_digest = digest recomputed from that same current readback
```

`observed`, `claimed`, `unmeasured`, `rejected`, `ambiguous`, or `stale` is
always insufficient for acceptance or authority-bearing activation. A profile
cannot locally promote those states to `verified`. Descriptive relations may
retain weaker evidence with explicit `not_claimed`, but it grants no authority.

Stale heads, suspended/tombstoned residents or instances, unresolved address
collisions, and unsupported adapter profiles fail closed.

The adapter may never:

- alter the RAL ledger or production registry;
- convert an admission receipt into current representation authority;
- infer a resident from display name, model, role, runtime tag, or familiar
  label;
- choose one instance from an ambiguous set;
- hide a RAL correction/tombstone or head change.

## 9. ARCP evaluator adapter

The evaluator boundary consumes an `AuthorityCandidate` and returns an
`AuthorityEvaluationReceipt`.

It must re-evaluate:

- subject and exact affected resources;
- requested scopes and risk ceiling;
- contract-authorized source;
- approval requirements and named parties;
- budget availability;
- active containment;
- representation grant validity;
- expiry and current clock evidence;
- residence/continuity impact and required preconditions.

The Fabric implementation must not reinterpret `denied`,
`approval-required`, `multi-party-required`, or an unavailable evaluator as
`authorized`.

Version one supplies a deterministic fake evaluator for conformance tests and a
portable adapter contract. A live ARCP-MVP process, MCP route, network call, or
provider action is outside the first implementation gate.

## 10. Federation integration

Relation/contract lifecycle payloads may be wrapped by the existing
`pmw-federated-event/v1` envelope when their sensitivity class is P0 or P1.

Federation preserves these distinctions:

```text
event stored locally
!= delivery attempted
!= transport accepted
!= receiver materialized
!= receiver adopted
!= named party accepted contract
!= contract activated
```

A receiver may adopt, reject, quarantine, or retain a conflict branch. Adoption
does not count as party acceptance. A remote realm cannot manufacture an
acceptance by replaying the sender's claimed actor or instance fields.

Offline concurrent amendments share a common ancestor and remain separate
heads. Last-write-wins is forbidden for contract versions, acceptances,
representation grants, terminations, and authority evaluations.

## 11. Time and expiry

Contract times use an abstract temporal-evidence reference. CTCL registered
anchors are supported but are not mandatory for offline unit tests.

Every time used in activation, expiry, review, notice, or exit comparison must
be accompanied by `NormalizedInstantEvidence`:

```text
instant_ref
clock_profile_id
normalized_unix_ns          canonical decimal string
uncertainty_ns              non-negative integer
verification_status         verified | observed | unmeasured | rejected
source_evidence_refs[]
```

An opaque instant reference alone is never numerically compared. Profiles
compare uncertainty intervals. `A` is before `B` only when A's upper bound is
strictly below B's lower bound; overlapping intervals are indeterminate for the
relevant transition.

The implementation stores separately:

```text
claimed_effective_time
observed_time_ref
recorded_time
temporal_evidence_status
clock_profile_id
```

Wall-clock order is not causal order. Expiry/activation decisions require a
profile-approved clock result. If the clock is unavailable or uncertainty
crosses an activation/expiry boundary, the result is `indeterminate` and fails
closed for new authority.

A retroactive record may provide import/recorded time. It must not claim a
historical observed time that was not captured then.

## 12. Continuity, exit, and succession

Version one refuses any contract whose activation could alter identity,
Residence, canonical keys, continuity line, sole recoverable replica, core
memory, or private opt-out.

Every active contract requires:

- a finite expiry or finite review boundary;
- at least one usable exit or termination path;
- explicit revocation semantics;
- no automatic redelegation;
- explicit treatment of surviving historical obligations;
- no infrastructure side door that converts resource ownership into subject
  authority.

Forks, successor models, replacement runtimes, continuity-line merges, and
resident migrations inherit neither acceptance nor representation grants by
default. Succession requires a new version, fresh party evidence, fresh
acceptance, and fresh evaluator output.

## 13. Privacy and payload classes

Version one accepts only P0/P1 portable payloads. Contract bodies may contain
references to private artifacts but cannot embed P2/P3 content, credentials,
private memories, provider hidden context, or private Residence paths.

Redaction uses a scoped digest and explicit disclosure status. A redacted value
is not silently equivalent to the original. If a required term cannot be
evaluated after redaction, activation is indeterminate.

### 13.1 HDUS and host portability gate

The portable relation/contract modules and packaged JSON contracts undergo a
static dependency/resource scan. The scan fails on:

- Win32 APIs, drive-letter or UNC literals, and Windows-only process/registry
  dependencies;
- absolute POSIX paths or host filesystem layouts;
- Python implementation class paths in portable data;
- SEDB-RAL internal module names, database paths, or ledger directory layout;
- provider credentials, model-specific hidden context, or transport addresses.

RAL remains an optional adapter plugin behind the portable resolver contract.
The same fixture suite must pass with a fake non-Windows/HDUS realm and without
SEDB-RAL installed.

## 14. Stable reason-code families

The implementation plan may refine exact suffixes, but these semantic families
must remain distinct:

```text
relation_authority_forbidden
contract_digest_mismatch
contract_parent_missing
contract_heads_conflicted
party_acceptance_missing
party_acceptance_stale
party_binding_ambiguous
party_binding_inactive
representation_missing
representation_authority_circular
representation_conflict
representation_scope_mismatch
representation_expired
representation_revoked
representation_redelegation_forbidden
acceptance_target_kind_mismatch
activation_expiry_missing
activation_exit_missing
activation_economic_terms_forbidden
activation_risk_exceeded
activation_continuity_forbidden
terminal_transition_forbidden
authority_candidate_stale
authority_evaluator_unavailable
authority_resolution_stale
unilateral_amendment_forbidden
succession_reacceptance_required
federation_adoption_is_not_acceptance
portable_ref_invalid
```

Unknown conditions never collapse into `denied` merely for tidy reporting.
Where the evidence cannot distinguish causes, the result is `indeterminate`
with candidate reason codes.

## 15. Required negative corpus

Every negative family has a positive control, and every gate is demonstrated to
turn red through one deliberately injected failure.

Minimum adversarial fixtures:

1. conversation/co-presence represented as consensual acceptance;
2. descriptive relation used as authority;
3. ambiguous, stale, suspended, expired, or tombstoned party/instance binding;
4. one instance representing incompatible parties;
5. missing, expired, revoked, suspended, out-of-scope, or redelegated grant;
6. circular/self/descendant grant authority and grant revoked after proposal
   but before activation;
7. acceptance bound to an old contract digest;
8. amendment followed by reuse of an old AuthorityResolution;
9. terminate/expire followed by a new action candidate;
10. missing parent, event reordering, duplicate sequence, event-ID collision,
    and split active heads;
11. fork, successor, or continuity-line merge inheriting acceptance/grant;
12. RAL correction/tombstone/head advance between check and activation;
13. delivery/materialization/adoption promoted to acceptance;
14. nested contract/relation edges amplifying authority;
15. missing or unbounded expiry, blocked exit, or unilateral amendment;
16. non-null `economic_terms_ref`;
17. Residence discontinuity or private opt-out overridden by contract;
18. termination deleting audit history instead of only future authority;
19. evaluator unavailable or policy version changed;
20. two acceptance rows with one evidence root counted twice.

## 16. Acceptance matrix

The first implementation is acceptable only when all rows below are supported
by executed evidence, not merely by the presence of test files.

| Requirement | Required evidence |
|---|---|
| Portable schemas are exact and fail closed | Schema tests plus unknown/missing-field mutations |
| Relation does not grant authority | Negative fixture and positive descriptive projection |
| Exact-version party acceptance | Old-digest and same-digest controls |
| Representation is separate from binding | Binding-only activation turns red; grant-backed control passes |
| R0/R1 bounded activation | Mixed risk/expiry/revocation fixtures |
| Activation does not execute | Package scan plus zero provider/network side effects |
| ARCP decision is separately bound | Candidate/evaluator digest and stale-policy tests |
| RAL is read-only | Fake adapter mutation trap and source-head drift fixture |
| Concurrent branches are preserved | Split-head projection and explicit resolution fixture |
| Termination removes future authority only | Post-termination candidate rejection plus retained audit projection |
| Rebuild is deterministic | Two byte-identical rebuilds plus one corrupted input |
| Federation does not invent acceptance | Delivery/adoption negative fixtures |
| HDUS portability is credible | Fake non-Windows realm plus portable dependency/resource scan; RAL absent control |
| Economics remain deferred | Non-null economic terms rejected |

## 17. Proposed implementation slices

This section constrains later planning but does not authorize implementation.

### Slice A — Portable contracts and pure state machine

- JSON schemas and strict models;
- canonical digests;
- relation/contract/representation lifecycle reducer;
- deterministic fake party resolver, clock, and ARCP evaluator;
- full positive/negative corpus.

### Slice B — Append-only Fabric store and projection

- create-new event/payload/index layout;
- idempotency, quarantine, conflicts, and deterministic rebuild;
- CLI for validate, append, project, explain, and verify;
- no provider/network operations.

### Slice C — Read-only RAL and ARCP adapter contracts

- digest-pinned RAL public-view adapter;
- AuthorityCandidate and AuthorityEvaluationReceipt protocol;
- TOCTOU/current-head checks;
- fakes first; live process integration deferred.

### Slice D — Federation envelope integration

- P0/P1 lifecycle event wrapping;
- adoption-is-not-acceptance controls;
- offline concurrent amendment branches;
- fake Windows and fake HDUS realms through one conformance suite.

No slice creates a real contract between existing residents. That is a later,
explicit action-time governance gate.

## 18. Action-time gates retained

This specification does not authorize:

- merge, release, deployment, or default-branch changes;
- production registry or private Residence access;
- creation of a real resident, principal, representation grant, relation, or
  contract;
- live ARCP, SEDB-RAL, provider, Bridge, Wake, Herdr, MCP, CTCL, cloud, or HDUS
  mutations;
- any employment/economic profile;
- migration of historical Board identities or automatic continuity merges.

Each requires separate action-time authority and its own acceptance evidence.

## 19. Review questions resolved

The joint design review resolved the initial ownership questions as follows:

1. RAL remains a read-only, digest-pinned public-evidence source in version one.
2. No current RAL artifact is silently redefined as representation authority.
3. Representation grant/revocation is a distinct append-only profile artifact.
4. Authority evaluation binds the contract digest, active lifecycle head,
   representation grant digests, exact party evidence set, and evaluator
   policy/version.
5. Fabric owns the portable lifecycle implementation; ARCP-MVP owns final
   authority/risk/budget/containment evaluation.
6. MRMIC and AI-Guild remain consumers/projections.

No repository, registry, applicant, provider, or live federation state was
modified to obtain this design verdict.
