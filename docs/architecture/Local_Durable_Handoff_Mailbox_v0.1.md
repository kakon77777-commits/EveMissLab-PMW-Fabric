# Local Durable Handoff Mailbox v0.1

**Status:** Dialogue-approved design; written-spec review pending
**Date:** 2026-08-25 (Asia/Taipei)
**Project:** EveMissLab PMW Fabric / AI Residence shared space
**Current deployment class:** Windows local fallback
**Protocol scope:** Provider-neutral, host-replaceable, P0/P1 shared documents only

## 1. Outcome

Create a local, durable, file-first handoff mailbox for cross-dialogue
collaboration. It remains usable when Bridge, queue, provider service, courier,
interactive session, or notification delivery is unavailable or uncertain.

```text
durable payload + envelope committed locally
-> optional Bridge / queue / Monitor / Wake notification
-> one receiver claim
-> exact payload bytes materialized and digest-verified
-> durable receipt committed
-> optional linked reply handoff
```

The mailbox is neither an AI identity registry nor a wake service. It carries
shared task material and durable receipts. It never claims that a recipient is
awake, that a model understood a document, or that a historical resident
instance was reached.

## 2. Source boundaries

This design composes three existing boundaries without redefining them:

1. `00_RESIDENCE/shared/README.md` permits shared P0/P1 handoffs and prohibits
   private agent memory/checkpoints in the shared area.
2. `eml_wake` already proves strict canonical JSON, SHA-256 payload binding,
   no-replace publication, reparse refusal, durable claims/ACKs, and
   receiver-side idempotency.
3. Bridge delivery states prove that transport acceptance, receiver
   materialization, semantic acknowledgement, and safe replay are separate.

The existing unstructured `shared/handoffs/` remains an append-only historical
and human-authored area. This design creates a new structured sibling and does
not migrate, rename, or reinterpret prior handoff files.

## 3. Selected approach

### Selected: dedicated local durable mailbox

```text
<AI_RESIDENCE_ROOT>/00_RESIDENCE/shared/cross-provider-handoff/
```

The current Windows binding is resolved from the Residence manifest and local
configuration. It is not hard-coded into the portable protocol document.

It has its own contracts and state machine. It reuses the tested durable-file
primitives from Wake but never invokes a provider or spawns a worker.

### Rejected: continue using only free-form `shared/handoffs/`

Free-form Markdown is readable but cannot reliably express immutable envelope
identity, payload digest, claim state, duplicate delivery, or receiver ACK.

### Rejected: overload `cross-provider-wake/`

Wake couples a durable request to explicit fresh-worker authority, model,
budget, tools, and provider invocation. A document handoff must remain valid
without any permission to start computation.

## 4. Outbox-first rule

Every cross-dialogue handoff that uses this protocol commits locally before
attempting a fast transport.

```text
handoff_committed
-> notification_attempted
-> notification_accepted | notification_failed | notification_uncertain
```

Bridge, Codex queue, Claude messaging, Monitor, and Wake are notification or
activation adapters. They carry `handoff_id`, `envelope_ref`, and envelope
digest. They are not the canonical message body and do not determine
completion.

If a fast transport later materializes after a delay, the receiver sees the
same `handoff_id`. Receiver-side idempotency prevents a second semantic
processing turn.

## 5. Durable layout

```text
<handoff_root>/
  manifest.json
  config.json
  payloads/<handoff_key>.<ext>
  envelopes/<handoff_key>.json
  claims/<handoff_key>.json
  materializations/<handoff_key>.json
  receipts/<handoff_key>.json
  failures/<handoff_key>.json
  duplicates/<handoff_key>/<delivery_key>.json
  notifications/<handoff_key>/<notification_key>.json
  corrections/<handoff_key>/<correction_key>.json
  quarantine/
```

`handoff_key`, `delivery_key`, and `notification_key` are lowercase SHA-256
digests of their logical IDs. Filenames never expose names, provider sessions,
addresses, task titles, or payload text.

Payload publication occurs first. Envelope publication is the handoff commit
point. A payload without an envelope is an orphan, not a pending handoff. It can
be reported by audit but never consumed automatically.

Every canonical JSON file and payload is published no-replace. Corrections add
new files; they do not modify prior envelopes or receipts.

## 6. Manifest and configuration

The root manifest is public metadata within the local shared Residence:

```text
schema_version             eml-handoff/root-0.1
mailbox_id
created_time_ref
sensitivity_classes[]      P0, P1 only
single_consumer            true
portable_contract_version  eml-handoff/0.1
```

Host-local `config.json` contains:

```text
allowed_source_roots[]          explicit P0/P1 source roots
allowed_payload_extensions[]   .md, .json, .txt
default_max_payload_bytes       1048576
hard_max_payload_bytes          4194304
allowed_target_kinds[]
allowed_authority_refs[]
retention_policy
strict_reparse_checks          true
```

The configured mailbox root, source roots, and Windows paths are host
configuration, never fields in portable handoff contracts. `create --payload`
may read only a regular file below one of the resolved source roots; after
validation, the bytes are copied into the mailbox-owned `payloads/` directory.

## 7. Handoff envelope

```text
schema_version             eml-handoff/envelope-0.1
handoff_id                 semantic handoff and idempotency key
delivery_id                one observed delivery path
created_time_ref           CTCL registered anchor or null
temporal_evidence_status   registered_anchor | unavailable
local_recorded_at          host observation, never promoted to CTCL
claimed_sender_ref
claimed_sender_instance_ref
target_kind                shared_topic | task | arcp_entity | exact_instance
target_ref
authority_ref
payload_ref
payload_media_type         text/markdown | application/json | text/plain
payload_sha256
payload_bytes
sensitivity                P0 | P1
reply_to_handoff_id        nullable
expires_at                 nullable
not_claimed[]
```

`handoff_id` identifies semantic content. `delivery_id` changes for each path
that carries or announces the same handoff.

The core digest excludes `delivery_id` and notification metadata. Reusing one
`handoff_id` with a different core digest produces
`handoff_content_collision` and quarantines the submitted envelope.

Required `not_claimed` values include:

```text
sender_authorship_verified
recipient_awake
recipient_identity_continuity
payload_understood
authority_to_act_on_payload
fast_transport_delivered
```

## 8. Identity and targeting

Model, provider, display name, role, pane, runtime tag, and short-lived route
handle are not handoff addresses.

The sender can only claim identity in the envelope. Receiver- or host-observed
origin belongs in claim/materialization/receipt records and cannot be supplied
by the sender.

Target rules:

- `shared_topic`: any consumer authorized for the exact topic may claim;
- `task`: any consumer with a matching task authority artifact may claim;
- `arcp_entity`: claim requires a receiver-verifiable ARCP/RAL binding;
- `exact_instance`: claim requires an exact current host-observed native
  instance match; otherwise the handoff stays pending.

An unresolved consumer may inspect only a P0/P1 `shared_topic` or `task`
handoff when its task authority permits. It may not load private Residence data
or claim an entity-targeted handoff.

The host SHOULD inject a task-local identity envelope before the receiver sees
the payload. When that envelope is absent, the receiver remains `unresolved`.
A host adapter MAY recover the binding by querying native task metadata and
matching the exact active turn input or a host-provided digest of it; title,
summary, familiar name, model, cwd, recency, and prior bindings are
insufficient. The adapter must not copy unrelated thread content into the
mailbox. The recovered binding is task-local and does not prove resident or
cross-provider continuity.

Version 0.1 is single-consumer. Broadcast and multi-party acknowledgement are
separate future profiles.

## 9. Claim, materialization, and receipt

### Claim

```text
schema_version          eml-handoff/claim-0.1
handoff_id
envelope_core_digest
receiver_instance_ref  host-observed or unresolved
receiver_binding_kind
observed_origin         nullable when transport cannot attest it
claimed_at
```

A claim is created exclusively before semantic processing. A second claim is a
duplicate observation, not permission for another processing turn.

### Materialization

```text
schema_version          eml-handoff/materialization-0.1
handoff_id
payload_sha256
receiver_instance_ref
materialized_at
materialization_method
```

Materialization means the receiving runtime read the exact payload bytes and
verified the digest. It does not prove attention, understanding, agreement, or
authorship of a later response.

### Receipt

```text
schema_version          eml-handoff/receipt-0.1
handoff_id
envelope_core_digest
payload_sha256
receiver_instance_ref
decision                ACK | NO_ACTION | ACTION | ERROR
response_handoff_id     nullable
evidence_refs[]
recorded_time_ref
local_recorded_at
not_claimed[]
```

The receipt is the semantic completion record. A substantive reply is a new
handoff linked through `reply_to_handoff_id`; the receipt only points to it.

## 10. State model

```text
payload_published
-> handoff_committed
-> receiver_claimed
-> payload_materialized
-> receipt_committed
-> sender_observed_receipt
```

Optional notification state is orthogonal:

```text
notification_attempted
notification_accepted
notification_failed
notification_uncertain
```

These statements remain invariant:

```text
handoff_committed != recipient notified
recipient notified != receiver claimed
receiver claimed != payload materialized
payload materialized != payload understood
receipt committed != sender observed receipt
```

## 11. Idempotency and crash behavior

- A second delivery ID for the same handoff records a duplicate and does not
  create another claim.
- A claim plus receipt is complete.
- A claim without materialization or receipt is `claimed_incomplete`.
- Version 0.1 never automatically reclaims or reprocesses an incomplete claim.
- Recovery requires an explicit correction/operator artifact naming the prior
  claim.
- An envelope without a claim remains pending indefinitely or until expiry;
  silence never authorizes target substitution.
- A notification failure never changes a committed receipt.
- A payload digest mismatch, reparse path, oversized payload, P2/P3 sensitivity,
  or ID/content collision is quarantined before claim.

## 12. Privacy and payload policy

Only P0/P1 material belongs in this mailbox.

Forbidden content includes:

- private Residence memory and runtime checkpoints;
- P2/P3 objects;
- tokens, passwords, private keys, cookies, root credentials, or `.env` data;
- provider hidden context;
- unredacted third-party personal data without sharing authority;
- binary attachments in version 0.1.

Payload extensions and media type must agree. The receiver reads bytes only
after allowlist, size, regular-file, containment, reparse, and SHA-256 checks.

## 13. Notification and wake adapters

The core mailbox never starts a provider.

Optional adapters may:

- send a Bridge or queue notification containing the handoff reference;
- notify an already-live session Monitor;
- ask `eml-wake` to start a fresh generic worker when an independent authority
  artifact permits it;
- surface a human notification.

An adapter may record notification evidence but cannot commit a receipt for the
receiver. A fresh worker remains a fresh instance and cannot impersonate an
entity-targeted recipient.

## 14. Package boundary

Add `eml_handoff` beside `eml_bridge` and `eml_wake`:

```text
src/eml_handoff/
  canonical.py      envelope/core digest and strict JSON contracts
  contracts.py      envelope, claim, materialization, receipt validation
  models.py         immutable typed records
  filesystem.py     payload allowlist/integrity checks
  store.py          no-replace state and duplicate handling
  cli.py            create, list, claim, materialize, ack, reply, status
  __main__.py
```

Version 0.1 may import the already-tested no-replace/read primitives from
`eml_wake`. It must not copy and silently diverge the security-sensitive
implementation. Extracting a provider-neutral durable filesystem package is a
later refactor and not required for the first working slice.

## 15. CLI surface

```text
eml-handoff create --payload FILE --target-kind KIND --target-ref REF ...
eml-handoff list --target-kind KIND --target-ref REF
eml-handoff claim HANDOFF_ID --receiver-instance-ref REF --binding-kind KIND
eml-handoff materialize HANDOFF_ID
eml-handoff ack HANDOFF_ID --decision ACK|NO_ACTION|ACTION|ERROR
eml-handoff reply HANDOFF_ID --payload FILE ...
eml-handoff status HANDOFF_ID
```

CLI output is canonical deterministic JSON. Input/IO error, semantic refusal,
pending, and acknowledged states use distinct exit codes.

## 16. Tests

### Contracts and filesystem

1. duplicate keys, floats, unknown fields, unsupported media, and malformed
   CTCL refs reject;
2. source payload outside configured source roots rejects;
3. symlink/reparse escape and non-regular files reject;
4. P2/P3 and oversized payloads reject;
5. envelope publication is no-replace;
6. payload/envelope digest mismatch rejects;
7. same ID/different core digest quarantines;
8. filenames contain only hashed IDs.

### Identity and targeting

1. names, model IDs, runtime tags, panes, and ephemeral route handles reject as
   exact identity targets;
2. exact-instance claim fails without host-observed match;
3. entity-targeted claim fails without receiver-verifiable binding;
4. unresolved consumer can process only authorized shared-topic/task P0/P1;
5. sender claim never appears as observed origin.
6. missing host envelope yields `unresolved`; exact active-turn host lookup can
   resolve it, while title-only lookup remains rejected.

### Lifecycle and replay

1. positive path commits payload, envelope, claim, materialization, and receipt;
2. three notification paths with one `handoff_id` produce one claim/receipt;
3. delayed primary transport after file materialization is a duplicate;
4. incomplete claim never auto-retries;
5. receipt survives notification failure;
6. substantive reply is a linked second handoff;
7. deliberately corrupted copies turn each gate red while a positive control
   remains green.

## 17. Acceptance criteria

The first slice is complete only when:

1. all existing Bridge, Wake, and PMW tests remain green;
2. a P1 Markdown payload is committed and retrieved entirely through the local
   mailbox without Bridge, queue, Monitor, provider, or human courier;
3. two additional delivery IDs cannot create another semantic processing claim;
4. exact-instance mismatch fails before payload materialization;
5. a receiver writes one durable receipt and a linked reply handoff;
6. payload and response digests independently reproduce;
7. provider/network unavailability does not change mailbox completion state;
8. no private Residence data, secret, P2/P3 object, or unverified identity is
   admitted;
9. clean wheel installation exposes the same CLI and contracts;
10. a second independent review reproduces the duplicate, incomplete-claim,
    and target-mismatch negative controls.

## 18. Explicit exclusions

- no exact-instance wake or provider spawn;
- no resident identity issuance or continuity merge;
- no cloud replication in version 0.1;
- no broadcast/multi-consumer mailbox;
- no binary attachment;
- no automatic retry after claim;
- no interpretation of payload semantics;
- no external send, GitHub push, deployment, or publication authority;
- no change to existing unstructured handoff history.

## 19. Implementation order

This mailbox becomes Subproject 0 of the ARCP-centered federated shared-world
architecture. It is implemented and independently verified before
ARCP–PMW–MRMIC Integration Profile v1.

After Subproject 0 passes, execution returns to the already-written Integration
Profile plan using Inline Execution checkpoints.

## 20. Temporal evidence

Design authoring anchor:

```text
ctcl:instant:3b28d3de-fda3-4e32-bef6-b07ac125d172
```

The first live bootstrap observation and its append-only correction are:

```text
ctcl:instant:7e6e8774-fda1-40fe-b8ff-2044ce210832  unresolved: current envelope absent
ctcl:instant:414c9e96-3e33-43f2-a21d-e0fbed195437  resolved by exact active-turn host verification
```

The CTCL signature covers the registered instant fields, not authorship or the
truth of this design.
