# Federated Event and Sync Profile v1

**Status:** Neo.K-approved written specification; J0 joint ownership seam approved; Wave 1 implementation authorized
**Date:** 2026-08-25  
**Project:** EveMissLab PMW Fabric  
**Parent architecture:** `ARCP_Centered_Federated_Shared_World_Architecture_v0.1.md`  
**Implementation position:** Subproject 2, after Local Durable Handoff v0.1 and ARCP–PMW–MRMIC Integration Profile v1

## 1. Decision

EveMissLab PMW Fabric will add a portable, append-only federated event and
reconciliation layer. A Windows host, cloud realm, future HDUS host, or embodied
realm may produce and exchange events without any realm becoming the universal
home of an AI entity.

Version 1 solves one bounded problem:

```text
two replicas may work offline
→ exchange immutable events later
→ verify provenance and causal structure
→ adopt, reject, quarantine, or retain an explicit conflict branch
→ never erase either history to manufacture agreement
```

It does not implement general consensus, identity issuance, autonomous
contracts, employment, or a universal merge algorithm.

## 2. Existing foundations

The profile consumes, but does not replace:

- ARCP/AREC entity and governance references;
- SEDB-RAL claims, observations, corrections, and authority artifacts;
- PMW workspace, task, resource, decision, and provenance semantics;
- Local Durable Handoff as the provider-free outbox and document carrier;
- Bridge/queue/Monitor as optional notification transports;
- Wake as an optional fresh-worker activation adapter;
- CTCL registered anchors as time evidence, not authorship or causal proof;
- MRMIC Phase 13 as a visual projection consumer, not the event authority.

### 2.1 J0 joint ownership seam

SEDB-RAL remains the sole canonical owner of registry facts, registry-effective
authority state, admission decisions, the registry ledger/head, production root,
checkpoint/recovery semantics, and public-disclosure decisions. PMW Fabric is
the sole canonical owner of portable carrier events, realm/replica mechanics,
adapter visibility, delivery/materialization observations, receiver adoption,
and cross-realm reconciliation records.

The seam is versioned and digest-pinned:

```text
RAL-owned public projection bytes and schema
→ Fabric-owned adapter profile pinned by $id/version/source commit/SHA-256
→ Fabric event and receiver observation
```

Fabric never vendors a second canonical RAL schema, activates a RAL authority,
or rewrites a RAL head. SEDB-RAL may consume Fabric evidence through a small
digest-pinned integration fixture without absorbing the Fabric event schema.

## 3. Core invariants

```text
Event != Delivery
Event != Observation
Observation != Adoption
Adoption != Authority
Replica sequence != Global sequence
Wall-clock order != Causal order
Conflict != Corruption
Missing evidence != Negative evidence
Same subject reference != Same resident proof
```

Additional rules:

1. Events are append-only and immutable after publication.
2. Corrections, withdrawals, tombstones, and resolutions are new events.
3. `event_id` is stable across delivery paths; `delivery_id` is not.
4. Sender-authored origin fields remain `claimed_*`.
5. Receiver observations cannot be supplied by sender payload.
6. No adapter may expand its own authority envelope.
7. A realm outage yields `unavailable` or `unmeasured`, not fabricated failure.
8. Public fixtures use synthetic identities and realm identifiers only.

## 4. Scope and non-goals

### Included

- portable event envelope v1;
- realm and replica references;
- per-replica monotonic sequence checks;
- causal-parent DAG validation;
- immutable local event store;
- inventory and missing-event exchange;
- receiver-side import observations;
- deterministic reconciliation classification;
- explicit conflict branches and resolution events;
- correction, withdrawal, and tombstone event kinds;
- deterministic JSON projection and CLI;
- two-realm offline/reconnect acceptance fixture.

### Excluded

- resident ID issuance or identity merge;
- automatic continuity decisions;
- global total ordering;
- last-write-wins conflict erasure;
- distributed locks across realms;
- Byzantine consensus or proof-of-personhood;
- autonomous relation or contract activation;
- P2/P3/private Residence replication;
- binary attachments;
- live cloud deployment or provider calls in ordinary tests;
- salaries, employment, labor time, debt, or economic tokens.

## 5. Portable references

All event references use the same one-field/one-semantics discipline established
by the Integration Profile.

```text
RealmRef
  realm_id                 stable identifier in this federation profile
  realm_kind               windows_host | cloud_host | hdus_host | embodied_host | fixture
  issuer                   who assigned the realm reference
  verification_status      verified | observed | claimed | unmeasured | rejected
  evidence_refs[]

ReplicaRef
  replica_id               stable event-log replica identifier
  realm_id
  store_generation         immutable generation identifier
  verification_status
  evidence_refs[]
```

Realm and replica references identify event infrastructure, not an AI entity.
They must never appear in an `entityRef` field.

## 6. Event envelope v1

The canonical portable event has these fields:

```text
schema                     pmw-federated-event/v1
event_id                   semantic event and idempotency key
event_kind                 namespaced event kind
subject_ref                typed reference to the affected PMW/ARCP object
realm_ref                  RealmRef
replica_ref                ReplicaRef
replica_seq                positive monotonic integer within store_generation
causal_parents[]            zero or more event IDs
claimed_actor_ref          nullable sender claim
claimed_instance_ref       nullable sender claim
authority_ref              nullable authority-artifact reference
payload_ref                content-addressed relative reference
payload_sha256             uppercase SHA-256
payload_media_type         application/json | text/markdown | text/plain
created_time_ref           nullable CTCL registered-anchor reference
temporal_evidence_status   registered_anchor | unavailable | unmeasured
local_recorded_at          weak local insertion observation
correction_of              nullable event ID
withdraws                  nullable event ID
not_claimed[]              mandatory non-claims
```

Required `not_claimed[]` entries:

```text
actor_authorship_verified
resident_identity_continuity
global_causal_order
remote_adoption
authority_to_execute
payload_understood
conflict_resolved
```

`delivery_id`, route handles, process IDs, pane IDs, provider tokens, Windows
paths, and private Residence paths are forbidden in the portable event core.

## 7. Event identity and digest

The envelope uses a versioned canonicalization domain distinct from handoff and
wake records:

```text
canonicalization_version = pmw-federated-event-json-nfc-codepoint-v1
event_digest = sha256(domain || canonical_event_core)
```

The event core excludes only transport-specific delivery observations. Changing
payload digest, causal parents, actor claim, authority reference, realm,
replica, sequence, or temporal evidence changes the event digest.

The same `event_id` with a different core digest is quarantined as
`event_content_collision`; it is never treated as a duplicate.

## 8. Local store

Version 1 uses a provider-free file store:

```text
<sync-root>/
  manifest.json
  config.json
  payloads/<event-key>.<ext>
  events/<replica-key>/<sequence>-<event-key>.json
  observations/<event-key>/<observer-key>.json
  adoptions/<event-key>/<realm-key>.json
  rejections/<event-key>/<realm-key>.json
  conflicts/<conflict-key>.json
  resolutions/<conflict-key>/<resolution-key>.json
  quarantine/<event-key>/<record-key>.json
  inventories/<inventory-key>.json
```

Payload publication precedes event-envelope publication. The envelope no-replace
write is the event commit point. A payload without an event is an orphan and is
not advertised. Every state transition is an immutable record.

## 9. Causal model

The causal relation is the transitive closure of `causal_parents[]`.

- `A → B` only when B directly or transitively names A as a parent.
- Two events with no path in either direction are concurrent.
- Replica sequence orders insertions from one replica generation only.
- CTCL intervals may demonstrate that one observation predates another, but do
  not create a causal edge by themselves.
- Ledger insertion order never breaks a cross-realm causal tie.

Imports reject cycles, missing required parents, duplicate sequence ownership,
and a sequence that rewrites an existing event. Missing parents may remain
`pending_dependencies` only when explicitly listed in the inventory exchange.

## 10. Synchronization protocol

Synchronization is inventory-first and pull-oriented:

```text
local immutable inventory
→ compare remote inventory
→ request missing event IDs
→ fetch payload/envelope bytes
→ verify digest, schema, replica sequence, and causal parents
→ write receiver observation
→ classify reconciliation
→ optionally write adoption/rejection/conflict records
```

An inventory contains only event IDs, digests, replica ranges, causal heads,
payload sizes, sensitivity classes, and availability. It contains no payload
body, bearer token, private memory, or semantic identity proof.

Push notification may announce an inventory reference, but cannot itself mark
events observed or adopted.

## 11. Reconciliation outcomes

Every imported event receives one outcome:

| Outcome | Meaning |
|---|---|
| `adopted` | Event is valid, authorized for this projection, and non-conflicting |
| `parallel_branch` | Event is valid but concurrent with a local event |
| `conflict` | Two valid events assert incompatible values or transitions |
| `rejected` | Schema, policy, or authority rules refuse adoption |
| `quarantined` | Digest, identity namespace, causal graph, or immutable-key integrity failed |
| `pending_dependencies` | Required parent events are not yet present |
| `unmeasured` | Adapter evidence is insufficient to classify |

`conflict` preserves both events. A resolution is a new event that names every
conflict member and states its authority artifact. It does not edit either
original.

## 12. Conflict classes

Version 1 distinguishes:

1. `concurrent_nonexclusive` — both events may coexist;
2. `field_value_conflict` — same subject/field, incompatible values;
3. `state_transition_conflict` — incompatible next states;
4. `authority_conflict` — competing or revoked authority artifacts;
5. `identity_reference_conflict` — incompatible entity/instance bindings;
6. `causal_history_conflict` — missing, cyclic, or contradictory parents;
7. `content_collision` — same immutable ID, different digest.

Identity and authority conflicts always fail closed. They cannot be resolved by
timestamps, display names, model labels, or majority row counts.

## 13. Correction and withdrawal

- `correction` points to the corrected event and supplies a replacement claim.
- `withdrawal` states that an earlier claim is no longer asserted.
- `tombstone` states that a field, contract version, or identifier semantics is
  retired; it never deletes the referenced record.
- `resolution` closes a named conflict under a verifiable authority artifact.

Consumers derive current projection state from the complete chain. They must
not overwrite the historical row in place.

## 14. Authority boundary

Event transport never grants action authority.

```text
valid event
AND receiver-observed source evidence
AND any authority artifact required by that event kind is valid for the exact action and subject
AND authority not expired/revoked
AND local policy permits projection
→ adoption may occur
```

Pure observation events may be stored without mutation authority, but they do
not change the projected subject state. Mutation, resolution, correction, and
withdrawal event kinds require the authority declared by local policy.

Version 1 may adopt PMW state/projection events. It may not execute provider
actions, wake an AI, issue identity, or activate an autonomous contract.

## 15. Privacy and sensitivity

Only P0/P1 events and `.json`, `.md`, `.txt` payloads are portable in version 1.
Payloads must be UTF-8 text and pass the same reparse/source-root protections as
Local Durable Handoff.

P2/P3 data, private memories, provider hidden context, credentials, and private
Residence content fail before payload materialization. Redacted evidence uses a
scoped digest and never silently becomes the original value.

## 16. Adapter contract

Each realm adapter declares every field as:

```text
observable | relay_only | structurally_unavailable | unmeasured
```

`unmeasured` is the default and fails closed for adoption. Adapters expose
inventory/fetch operations only; notification and activation remain separate
ports. Windows, cloud, HDUS, and embodied adapters must pass the same portable
contract suite.

### 16.1 Adapter visibility evidence

An adapter read is a projection over host state, not the host state itself.
Version 1 therefore records `pmw.adapter-visibility-evidence/0.1` separately
from delivery and adoption. It distinguishes at least:

```text
execution_state        completed | incomplete | unmeasured
adapter_read_outcome   body_available | metadata_only | empty_projection |
                       read_failed | unmeasured
local_capture_state    body_observed | metadata_only | not_observed | unmeasured
materialization_state  verified | present_unverified | absent | unmeasured
portable_delivery_state acknowledged_structured | materialized | uncertain |
                        not_proven
authorship_state       receiver_observed | claimed | unmeasured
```

Required inference barriers are:

```text
turn_completed_does_not_imply_adapter_body_available
empty_projection_does_not_imply_no_response
local_capture_does_not_prove_portable_delivery
materialized_handoff_does_not_prove_original_adapter_delivery
delivery_or_materialization_does_not_prove_authorship_or_identity
no_automatic_resend_from_empty_projection
```

The motivating fixture is the exact Codex task incident where a completed turn
was returned twice with `items=[]`, while an exact local transcript contained an
assistant message and a digest-verified durable handoff existed. The correct
classification is `completed + empty_projection + body_observed(local_only) +
materialization verified + portable delivery not_proven + authorship unmeasured`.
The empty projection never authorizes automatic replay.

### 16.2 RAL public-projection adapter

The Fabric-owned RAL adapter manifest records the RAL schema `$id`, semantic
version, source commit, byte length, and SHA-256 plus explicit subject,
sensitivity, correction, and tombstone mappings. RAL owns `ral_disclosure_class`;
Fabric owns `fabric_payload_class` and realm-qualified carrier subjects. A
receiver adoption receipt records the receiver decision and evidence but has no
field that can mutate a RAL head, activate authority, or commit a registry
operation.

## 17. CLI surface

The first implementation exposes deterministic JSON commands:

```text
eml-pmw event-create --root DIR --config FILE --payload FILE --kind KIND --subject-ref REF --realm-ref FILE --replica-ref FILE
eml-pmw event-inventory --root DIR
eml-pmw event-diff LOCAL REMOTE
eml-pmw event-import --root DIR --event FILE --payload FILE --observer FILE
eml-pmw event-reconcile EVENT_ID
eml-pmw conflict-show CONFLICT_ID
eml-pmw conflict-resolve CONFLICT_ID --authority-ref REF --payload FILE
eml-pmw sync-status
```

Exit classes remain distinct:

```text
0 success/adopted
1 unreadable or malformed input
2 semantic rejection or quarantine
3 conflict/parallel branch
4 pending dependencies or unmeasured
```

## 18. Deterministic projection

The canonical file event log is authoritative. SQLite/JSON views are rebuildable
projections only. Rebuilding twice from the same event set must produce
byte-identical JSON and row-identical SQLite values.

Projection differences are classified as:

```text
expected_by_mapping | unmapped | contradiction
```

Only contradiction fails the gate. `unmapped` remains visible and cannot be
silently discarded.

## 19. Acceptance scenario

The minimum vertical test uses synthetic Realm A and Realm B:

1. both import the same genesis workspace/task state;
2. network availability becomes false;
3. A and B each append a different update to the same task field;
4. both append unrelated nonexclusive events;
5. connectivity returns;
6. inventories are exchanged;
7. missing events are imported with receiver observations;
8. unrelated events are adopted;
9. field updates produce one explicit conflict containing both event IDs;
10. a principal-authored resolution event selects or replaces the value;
11. both realms rebuild to the same projection;
12. original conflicting events remain byte-identical and queryable.

The fixture also injects:

- one payload digest mutation;
- one missing parent;
- one causal cycle;
- one replica-sequence collision;
- one authority revocation;
- one same-ID/different-core collision;
- one `unmeasured` adapter cell;
- one duplicate delivery through three notification paths.

Every red fixture has a positive control.

## 20. Completion criteria

Subproject 2 is complete only when:

1. all existing 211 source tests remain green;
2. canonical event and store schemas are package resources;
3. exact duplicate events process once under concurrent arrival;
4. cycles, sequence rewrites, and content collisions fail closed;
5. offline reconciliation preserves both conflicting histories;
6. resolution requires a receiver-verifiable authority artifact;
7. deterministic JSON and SQLite rebuilds match;
8. ordinary tests make zero network/provider/CTCL calls;
9. clean wheel installation exposes the same CLI and resources;
10. portability and credential scans remain green;
11. FCAO uses at most one Twin review seat for the final candidate;
12. merge requires GitHub matrix CI and a post-merge clean clone.
13. adapter visibility RED/GREEN fixtures prove completed-turn, body visibility,
    durable materialization, portable delivery, and authorship remain distinct;
14. the RAL seam verifies an exact external schema pin and rejects a changed
    digest before parsing or event creation.

## 21. Deferred work

The following belong to later subprojects:

- relation and contract state machines;
- provider action execution;
- Windows service/adapter consolidation;
- live MRMIC shared-world vertical operation;
- cloud production deployment;
- HDUS native host;
- employment and economic relations.

## 22. Review gate

Neo.K approved this written specification on 2026-08-25 and authorized one
implementation plan for this profile. Implementation uses one primary executor
and at most one FCAO Twin for necessary final checking; it does not use per-task
rotating reviewers. The implementation plan does not itself authorize push,
merge, deployment, provider calls, or expansion into later subprojects.

Neo.K subsequently approved the J0 joint ownership matrix, digest-pinned schema
seam, and adapter-visibility incident contract. That approval authorizes scoped
Wave 1 implementation, tests, commits, and routine branch push. Merge,
production registry layout mutation, a real applicant, live federation,
Herdr/Claude activation, private Residence access, and cloud/off-site replication
remain separate action-time gates.
