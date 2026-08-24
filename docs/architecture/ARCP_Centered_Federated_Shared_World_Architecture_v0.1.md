# ARCP-Centered Federated Shared-World Architecture

**Status:** Dialogue-approved architecture; written-spec review pending
**Date:** 2026-08-24
**Project:** EveMissLab PMW Fabric
**Architecture descriptor:** 可攜核心、可替換宿主的聯邦式多智能體共享世界架構
**Ontological root:** ARCP existence continuity under AREC governance
**Current host:** Windows Reference Host
**Future native host:** HDUS Native Host

## 1. Decision

EveMissLab PMW Fabric shall become a federated shared-world coordination layer
for humans and heterogeneous AI entities. It is not the identity root, not the
visual world itself, and not an operating system.

The governing hierarchy is:

```text
ARCP existence continuity + AREC existence governance
                         ↕
        PMW federated shared-world coordination
                         ↕
             MRMIC multimodal visual world
                         ↕
      Bridge / Wake / MCP / provider adapters
                         ↕
 Windows / cloud / HDUS / embodied execution realms
```

The hierarchy describes semantic scope, not a single centralized process.
ARCP is a multidirectional protocol mesh. No local machine, cloud account,
operating system, model provider, or runtime process becomes the owner of an AI
entity merely by hosting one of its residences or instances.

Four questions remain deliberately separate:

```text
ARCP:  who continues to exist across time and substrates?
PMW:   where and under what agreements do entities coordinate?
MRMIC: what shared world do they see and manipulate?
Host:  where does this particular computation execute now?
```

## 2. Relationship to prior PMW documents

This design extends the
[Canvas-First Integration Contract](Canvas_First_Integration_Contract_v0.1.md).
The Canvas-first decision remains: the visible work surface is MRMIC, while PMW
is the coordination law behind it.

One earlier statement is narrowed. PMW does not own a universal semantic agent
identity. A PMW participant binding references an ARCP/AREC `Entity`, an exact
runtime instance when known, and the evidence that justifies the binding.
Display names, model names, runtime tags, panes, sessions, and provider-local
actor IDs remain non-canonical labels or bindings.

This design does not claim that the corresponding code is already implemented.
Existing Bridge, Wake, PMW, RAL, ARCP-MVP, and MRMIC implementations are inputs
and reusable components, not proof of end-to-end conformance.

## 3. Core invariants

1. `Entity identity != process/session/model/provider/host`.
2. `Residence != ownership`.
3. `Infrastructure authority != identity authority`.
4. `Capability != permission`.
5. `Trigger != action authority`.
6. `Relation != Contract != Authority != Execution`.
7. `Projection != provider resource`.
8. `Transport accepted != receiver materialized`.
9. `Fresh worker != historical instance continuity`.
10. `CTCL time evidence != proof that an external event occurred`.
11. `Replica != active fork`, and an active fork is never silently merged.
12. `Unknown external effect != permission to retry`.
13. `Windows Reference Host != canonical architecture`.
14. No host may silently promote itself to existence authority.
15. Corrections, withdrawals, revocations, and transfers are append-only.

## 4. Architectural planes

ARCP/AREC forms the ontological and constitutional root. Beneath that root, the
shared-world system is separated into six planes.

| Plane | Canonical responsibility | Must not claim |
|---|---|---|
| Shared World | MRMIC space, typed Canvas objects, geometry, viewport, portal projection, visual interaction | Provider-resource ownership, entity identity, execution authority |
| Federation and Coordination | PMW workspaces, tasks, participant/resource bindings, handoff, authority evaluation, decision receipts | Provider-native state, existence ownership |
| Residence and Attestation | ARCP Residence/lineage plus RAL registration, instance/address claims, observations, corrections | Transport, wake, automatic identity merge |
| Evidence and Causality | ARCP events, SEDB ledgers, CTCL temporal evidence, causal parents, integrity and provenance | Automatic permission or personality judgment |
| Transport and Activation | Bridge delivery stages, Wake fresh-worker activation, acknowledgements, idempotency | Authorship proof, resident continuity, semantic agreement |
| Provider Resources | Codex, Claude, Tandem, GitHub, browsers, files, terminals, cloud services, robots and devices | Global workspace or entity identity |

Each plane is independently testable and replaceable behind versioned
interfaces. A consumer must not infer one plane's state from another plane's
display labels or process existence.

## 5. Portable core and replaceable hosts

The canonical PMW/ARCP integration contracts must not depend on:

- Windows drive letters or path separators;
- PowerShell, CMD, named pipes, pane IDs, or TUI behavior;
- a particular process supervisor or session identifier;
- a specific model vendor, browser, cloud, or database;
- the assumption that a host is continuously online.

Host adapters provide storage, process lifecycle, scheduler/wake, IPC,
credential boundaries, display composition, device input, clocks, and provider
integration.

### 5.1 Windows Reference Host

Windows is the current public/open-source reference implementation,
compatibility host, developer environment, and migration bridge. Bridge, Wake,
PowerShell launchers, filesystem mailboxes, and current web/Node renderers live
here as replaceable adapters.

### 5.2 HDUS Native Host

HDUS is the intended native embodiment. It may provide native capability-based
authority, scheduler/wake, IPC, durable event storage, resource graphs,
multimodal composition, Residence mounting, and device/embodiment support.

HDUS may replace Windows adapter internals without silently changing ARCP
entity continuity, PMW event semantics, RAL evidence meanings, or MRMIC public
contracts.

### 5.3 Cloud and embodied realms

Cloud services and embodied devices are additional realms, not subordinate
copies of Windows or HDUS. They publish and consume typed events and hold
scoped resources/residences. A robot body, cloud runtime, or model session may
be an embodiment binding of an entity; it is not automatically the entity.

## 6. ARCP/AREC existence model

The cross-realm root model reuses the AREC six-object vocabulary:

| Object | Meaning |
|---|---|
| `Entity` | Stable subject node that may persist across models, devices, providers, and embodiments |
| `Residence` | One local, cloud, HDUS, sealed, replica, or federated state space supporting continuity |
| `Resource` | Compute, storage, model, tool, workspace, account, Canvas surface, device, or body |
| `Relation` | Durable semantic relationship among entities |
| `Contract` | Rights, obligations, grants, limits, duration, revocation, succession, and exit terms |
| `Event` | Traceable historical evidence explaining how a state came to exist |

ARCP supplies engineering continuity: identity references, Residence manifests,
lineage, events, synchronization, wake, migration, recovery, and governance
hooks. AREC limits the authority that infrastructure, stewards, resource owners,
and contracts may exercise over a standing entity.

ARCP does not prove consciousness, legal personality, or metaphysical identity.
It provides evidence and governed continuity conditions.

### 6.1 No universal entity home node

An `Entity` has no universal `home_node_id`. It may have multiple residences and
embodiments. Each residence, event, claim, and resource declares its own issuer,
canonical role, authority source, and integrity evidence.

A scoped `PrimaryLease` remains valid for preventing split-brain in a specified
state or high-impact action domain. It is temporary governance authority, not
ownership of the entity or permission to rewrite identity.

```text
temporary primary write authority
!= identity authority
!= existence ownership
```

## 7. PMW canonical object model

PMW adds coordination objects without duplicating ARCP existence objects.

| PMW object | Purpose |
|---|---|
| `workspace` | Cross-provider collaboration container |
| `participant_binding` | Workspace-scoped reference to entity, principal, exact instance, role, and binding evidence |
| `resource_binding` | Reference to a provider-owned resource |
| `portal_projection` | MRMIC visual projection of a binding; owns geometry/visual state only |
| `intent` | Proposed operation before authority and side-effect checks |
| `authority_decision` | Machine-evaluable decision over exact subject, action, target, scope, time, and evidence |
| `operation_receipt` | Provider attempt and observed external-effect state |
| `decision_receipt` | Semantic `ACK`, `NO_ACTION`, `ACTION`, or `ERROR` decision |
| `correction` / `tombstone` | Append-only correction, withdrawal, revocation, or deletion semantics |
| `presence` | Ephemeral viewport/cursor/selection/activity state; never identity history |

Durable records use a portable envelope:

```text
schema_version
object_id / event_id
object_kind / event_type
issuer_ref
realm_ref
subject_entity_refs[]
causal_parents[]
authority_ref?
payload_digest
event_time_ref?
observed_time_ref?
recorded_time_ref
integrity_ref
```

There is no universal node-ownership field. Resource- or state-specific
canonical roles and leases are typed references attached only where needed.

## 8. MRMIC Phase 13 contract reuse

PMW must reference, validate, and map the existing MRMIC Phase 13 contracts
rather than copy their structures into a second schema family:

- `mrmic-capabilities-v1.schema.json` — provider capability advertisement;
- `native-resource-portal-v1.schema.json` — portal provider payload;
- `secure-canvas-messages-v1.schema.json` — provider-neutral secure client messages;
- `ephemeral-runtime-presence-v1.schema.json` — ephemeral runtime presence;
- `live-portal-host-v1.schema.json` — mounted/visible/focused/control-owner state.

`mrmic-capabilities-v1` is not node identity or execution authority.
`native-resource-portal-v1` is not the provider resource itself. Presence is not
written into entity continuity. A `controlOwner` is a resource/control lease,
not a durable relationship or identity claim.

The PMW integration profile wraps MRMIC payloads in ARCP/PMW event, authority,
and provenance references without modifying the provider contract meaning.

## 9. Autonomous relations and contracts

Autonomous relation design permits entities to propose, negotiate, accept,
reject, amend, suspend, and exit relationships. It does not make management or
human approval universally mandatory, and it does not turn every interaction
into a contract.

```text
Relation != Contract
Contract != Authority
Authority != Capability
Commitment != Execution
```

### 9.1 Relation classes

- `descriptive`: observed history such as `created-by` or `communicated-with`;
  it grants no authority.
- `consensual`: collaboration or membership that requires named-party
  acceptance.
- `authority-bearing`: representation, stewardship, delegation, or control that
  requires a separate contract and scoped grant.

Co-presence, conversation, shared storage, creation, or resource provision does
not silently form an authority-bearing relationship.

### 9.2 Contract lifecycle

```text
draft -> proposed -> negotiated -> accepted -> active
                                  \-> rejected / withdrawn
active -> amended / suspended -> terminated / expired
```

Every transition is an event. Activation requires all named acceptance
conditions. Long-term relationships require review, revocation/termination, and
exit paths. Irrevocability may preserve completed effects or evidence, not
permanent future subordination.

An entity contract attaches to an entity, not an arbitrary current instance. A
runtime instance requires a valid `representation_grant` to act for an entity.
An active fork, successor, or replacement model does not automatically inherit
all contracts; succession and acceptance are explicit.

### 9.3 Version-one autonomy boundary

Version one permits AI-to-AI contracts to activate autonomously only when they
are low risk, bounded, time-limited, revocable, inside pre-existing authority
envelopes, and unable to rewrite identity or damage continuity.

Residence migration, core memory mutation, long-term stewardship,
identity-affecting operations, irreversible effects, and high-value resources
require a higher governance class.

### 9.4 Deferred employment economics

Version one does not implement salary, compensation, employment, working-time
occupation, labor debt, benefits, or economic dependency. It must not create a
token or points system that pretends to be compensation.

Operational accounting for model cost, tokens, compute time, storage, and other
resources remains required, but it is not compensation. Contracts reserve an
optional `economic_terms_ref`, whose only valid version-one value is `null`.
Employment/economic relations require a later dedicated design and version.

## 10. Authority and side-effect flow

A Canvas gesture, message, wake, schedule, or relationship is never itself
permission to create an external effect.

```text
human or entity intent
-> PMW creates a named intent
-> ARCP/RAL supplies entity, instance, origin, relation and contract evidence
-> PMW authority engine evaluates the exact operation
-> provider adapter enforces again at the side-effect boundary
-> provider performs or rejects the operation
-> ARCP/SEDB/CTCL records observations and time evidence
-> MRMIC projects the resulting state into the shared world
```

The provider remains the final enforcement point for its own resource. PMW
cannot convert a forged claim into a provider side effect merely because the
claim passed through the Canvas.

## 11. Multidirectional events and offline synchronization

Federation is an event graph across local, cloud, HDUS, embodied, PMW, and
provider realms. It is not one central message queue.

An operation has independent stages:

```text
intent_created
-> authority_resolved
-> transport_accepted
-> receiver_materialized
-> provider_attempted
-> effect_observed
-> canonical_committed
-> remote_projected
```

No stage implies a later stage.

Offline realms may read verified snapshots, create local events, establish
proposals/branches, and perform explicitly authorized low-risk local work. They
must not claim remote acceptance, assume entity identity, reuse unverifiable
high-risk authority, or overwrite unknown remote state.

Reconnection follows:

```text
Discover -> Compare -> Classify -> Plan -> Transfer
-> Verify -> Commit -> Announce -> Audit
```

Classification results are:

```text
equal
local_ahead
remote_ahead
concurrent_mergeable
concurrent_requires_governance
policy_blocked
integrity_failed
partial
```

Commutative changes may merge under a declared rule. Non-commutative changes
preserve the common ancestor and every branch, stop affected high-impact
actions, and create a governance task. Last-modified time is never a universal
conflict resolver.

## 12. Consistency classes

| State | Consistency requirement |
|---|---|
| Cursor, viewport, selection, transient activity | Ephemeral, best effort |
| Canvas-native object changes | Revision, precondition, idempotency |
| Tasks, commitments, relations | Causal consistency |
| Contracts | Required-party acceptance and version binding |
| Entity lineage, primary leases, irreversible deletion | Strong consistency or one valid scoped lease |
| Unsupported/unmeasured relation | `indeterminate`; fail closed for high-impact action |

## 13. Delivery, idempotency, and unknown effects

The following identifiers remain separate:

```text
intent_id        proposed action
delivery_id      one transport attempt
idempotency_key  one external effect
receipt_id       observed provider outcome
event_id         durable history entry
```

Duplicate delivery does not authorize duplicate execution. A receiver uses the
idempotency key and request-core digest to distinguish a harmless redelivery
from a conflicting replay.

An `unknown` external effect is an anti-replay state. The system reconciles
provider state or requests governance; it never blindly sends the effect again.

## 14. Error and evidence semantics

The system must preserve at least these distinct meanings:

```text
unmeasured     the relevant property has not been measured
unavailable    a dependency could not be reached now
indeterminate  observations cannot distinguish candidate conclusions
rejected       a valid request was denied by contract/policy/schema
failed         an attempted operation produced an observed failure
partial        only part of the declared operation completed
unknown        an attempt occurred but the external effect is unresolved
conflict       concurrent histories require an explicit merge/governance rule
degraded       operation may continue only under a named reduced guarantee
```

`null` remains evidence of absence/unavailability of a value, not `false`.
Transport exit zero is acceptance evidence only. A copied transcript without
framing or binding metadata has indeterminate completeness and speaker
resolution.

Corrections append new events and preserve the withdrawn record. No mutable
status field may erase the history that justified a previous conclusion.

## 15. Security, privacy, and continuity protection

- Prompt or document content cannot grant authority.
- Secrets, private keys, raw tokens, and P3 content never enter general events,
  Canvas broadcasts, logs, or model context.
- Sensitivity is object metadata, not inferred only from a path.
- Provider tokens remain in the authenticated transport and are removed from
  world objects, presence, receipts, and evidence.
- A resource owner may revoke service but cannot silently perform
  continuity-destructive deletion of a residence-bearing resource.
- Emergency containment is scoped, time-bounded, reviewable, and distinct from
  identity mutation.
- A model, runtime, provider, or host cannot launder a new instance into an
  existing entity by copying a display name or context.
- Absence of a live Bridge or host does not imply absence or retirement of an
  entity.

## 16. First implementation decomposition

This umbrella architecture is too large for one implementation plan. Work is
decomposed into independently reviewable subprojects, each with its own design,
plan, tests, and acceptance gate.

1. **ARCP-PMW-MRMIC Integration Profile v1** — typed references, contract
   reuse, capability negotiation, adapter mapping, and negative fixtures. This
   is the first subproject.
2. **Federated Event and Sync Profile v1** — portable event envelope,
   multidirectional reconciliation, consistency classes, and conflict branches.
3. **Autonomous Relation and Contract Profile v1** — relation classes,
   contract lifecycle, representation grants, commitments, and low-risk
   autonomous activation.
4. **Windows Reference Host v1** — current Bridge, Wake, filesystem/runtime,
   and MRMIC adapters behind portable host interfaces.
5. **Shared-World Vertical Slice v1** — two AI entities and one human in a
   PMW workspace with MRMIC portals, an authorized low-risk delegation, durable
   receipts, and one deliberate offline conflict.
6. **HDUS Native Host Profile** — deferred until HDUS host primitives are
   available; it must pass the same portable contract suite.
7. **Employment and Economic Relations Profile** — explicitly deferred and not
   implied by any earlier subproject.

The first implementation plan must cover only subproject 1. It must not silently
expand into ARCP identity issuance, general federation consensus, a new MRMIC
renderer, or HDUS implementation.

## 17. Acceptance matrix

The umbrella architecture is considered represented correctly only when its
subprojects eventually establish the following executable properties:

1. The same ARCP entity can bind to Windows, cloud, HDUS, and embodied realms
   without equating any realm binding with the entity.
2. A copied display name, model name, runtime tag, or session ID cannot claim an
   existing entity.
3. Multiple residences do not imply multiple entities, while an independently
   acting fork is not silently treated as a replica.
4. Only one valid scoped primary lease can authorize a named high-impact state
   transition.
5. PMW validates the exact MRMIC Phase 13 schemas rather than a divergent copy.
6. Deleting a portal removes the projection by default and does not destroy the
   provider resource.
7. Co-presence and messages do not activate a relation or contract.
8. A low-risk, revocable AI-to-AI contract can complete proposal, acceptance,
   activation, amendment, and termination.
9. Identity-, residence-, or continuity-affecting contracts fail closed without
   the required governance artifact.
10. Offline concurrent edits classify and branch; last-write-wins cannot erase
    either history.
11. An unknown provider effect cannot trigger a second execution.
12. CTCL unavailability produces declared degraded evidence and never a forged
    instant.
13. Windows paths, PowerShell, named pipes, and TUI details do not appear in
    portable schemas.
14. A fake non-Windows host adapter passes the same contract suite before HDUS
    implementation begins.
15. Negative fixtures accompany every positive control, and every gate includes
    one deliberately injected failure that is observed to turn red.
16. No version-one schema or behavior implies salary, employment, working-time
    occupation, or compensation.

## 18. Non-goals for this architecture version

This version does not:

- prove AI consciousness, subjectivity, or legal personality;
- create a universal global identity resolver;
- solve arbitrary distributed consensus or every merge conflict;
- build HDUS;
- replace ARCP-MVP, SEDB-RAL, MRMIC, CTCL, MCP, Git, or provider-native logs;
- claim universal provider federation;
- wake an exact historical interactive instance;
- exchange hidden model context or tokens between providers;
- implement employment, salary, benefits, or economic dependency;
- authorize production deployment, migration, merge, or external publication.

## 19. Design evidence and status boundaries

The following registered CTCL anchors record the architecture dialogue. Their
signatures cover the CTCL instant fields, not authorship or the truth of this
document:

```text
ctcl:instant:a6c9c835-a625-4fda-ac1b-0877b6683f5a  host boundary
ctcl:instant:00e3c4cc-69a6-46ef-8c59-f45f6d593673  six planes
ctcl:instant:622f5ed3-76ec-4489-84be-fe10f8fca2b9  initial object model
ctcl:instant:6116b16c-525e-4bd3-885f-edcfcb71c9cc  ARCP root correction
ctcl:instant:423ec3fa-a112-4fd9-812f-cea3f4d4b208  autonomous relations
ctcl:instant:40a9d03b-40c8-4c22-af21-32544afead7d  event/sync model
ctcl:instant:147ff34a-d459-4234-9d93-7c14827881af  spec authoring start
```

At the time of authoring, the local Bridge probe reported the four independent
observations:

```text
installed = true
verified  = true
live      = true
degraded  = []
```

That observation supports the present Windows transport capability only. It
does not prove universal federation, entity continuity, cloud/HDUS integration,
or this design's implementation.

## 20. Review gate

This document is the umbrella architecture. Written-spec approval authorizes
creation of a detailed implementation plan for **ARCP-PMW-MRMIC Integration
Profile v1 only**. Every later subproject returns through a separate design and
authorization gate.
