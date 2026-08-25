# EveMissLab PMW Fabric

EveMissLab PMW Fabric is a Canvas-first, provider-neutral collaboration fabric
for humans and multiple AI systems. The current public foundation supplies
workspace semantics, a journaled cross-provider Bridge, and a durable external
wake path. The infinite Canvas shared world is the next product horizon, not a
claim about the current release.

## Public status

Implemented and tested:

- PMW workspaces, tasks, semantic agents, resource bindings, presence,
  decisions, and provenance references;
- Bridge framing, journaled delivery, structured reply capture, and target
  authority locks;
- durable fresh-worker wake with strict authority, model, tools, budget,
  timeout, digest, CTCL, and idempotency boundaries.
- Local Durable Handoff Mailbox v0.1 with outbox-first P0/P1 documents,
  immutable claims/materializations/receipts, and duplicate-delivery control.
- ARCP–PMW–MRMIC Integration Profile v1 with exact Phase 13 schema locks,
  typed entity/instance references, fail-closed capability negotiation, native
  resource portals, and an offline conformance CLI.
- Federated Event and Sync Profile v1 with immutable realm/replica events,
  inventory-first offline exchange, causal conflict preservation, explicit
  authority-bound resolution, adapter-visibility evidence, and a digest-pinned
  SEDB-RAL public-projection seam.

Planned work is tracked in [ROADMAP.md](ROADMAP.md). The canonical design for
the shared visual world is
[the Canvas-first integration contract](docs/architecture/Canvas_First_Integration_Contract_v0.1.md).
Security boundaries are documented in
[docs/security/SECURITY_BOUNDARIES.md](docs/security/SECURITY_BOUNDARIES.md),
and the portable wake procedure is in
[docs/operations/WAKE_QUICKSTART.md](docs/operations/WAKE_QUICKSTART.md).
The provider-free file fallback is specified in
[docs/architecture/Local_Durable_Handoff_Mailbox_v0.1.md](docs/architecture/Local_Durable_Handoff_Mailbox_v0.1.md).
The portable hierarchy from ARCP/AREC existence governance through PMW
coordination to the MRMIC visual world is defined in
[docs/architecture/ARCP_Centered_Federated_Shared_World_Architecture_v0.1.md](docs/architecture/ARCP_Centered_Federated_Shared_World_Architecture_v0.1.md).
The offline federation contract is
[docs/architecture/Federated_Event_and_Sync_Profile_v1.md](docs/architecture/Federated_Event_and_Sync_Profile_v1.md).

## Install and verify

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[test]"
.venv\Scripts\python -m unittest discover -s tests
```

Ordinary tests are offline. The real provider/CTCL probe is opt-in and is not
run by public CI.

## Architecture

This package is the first executable Canvas-first PMW Fabric.

It keeps the previously verified Herdr Bridge runtime and adds a provider-neutral layer above it:

```text
PMW Fabric
├── semantic agents
├── verified provider bindings
├── logical workspaces
├── cross-provider tasks
├── resource bindings
├── ephemeral presence
├── decision receipts
├── provenance refs
├── immutable federated events and deterministic reconciliation
└── adapters
    ├── Herdr Bridge importer
    ├── legacy MRMIC Phase 12 HTTP projection
    ├── secure MRMIC Phase 13 native-portal projection
    └── deterministic mock visual world
```

## Key rule

```text
Canvas projection != provider resource
provider-local identity != semantic identity
presence != durable state
transport outcome != decision receipt
```

## Deterministic integrated demo

```bash
python -m eml_pmw demo --demo-dir run/pmw-demo
```

The demo creates a shared PMW workspace containing:

- Neo.K
- Claude
- Codex
- two independently-owned Tandem browser resources
- two Herdr runtime resources
- four visual portals
- three simultaneous presence records
- one ACTION decision receipt

The demo uses MockHerdr and MockVisual adapters. It proves Fabric state semantics; it does not claim live Tandem/MRMIC execution.

## MRMIC compatibility profiles

`MRMICHTTPAdapter` preserves the legacy Phase 12 `compat_frame_v0` path. Phase
12 actor fields remain untrusted payload data, so that adapter still refuses
live external AI-presence injection.

`MRMICPhase13Adapter` is a separate opt-in HTTPS bearer adapter. Before any
authenticated mutation it retrieves `/api/capabilities`, validates the exact
vendored Phase 13 contract surface, and fails closed unless
`native_resource_portal_v1` and `bearer_principal_v1` are both available.

Offline conformance check:

```powershell
python -m eml_pmw profile-validate examples/integration/profile-v1-positive.json
```

ARCP/AREC is the existence and governance root; PMW is the shared-world
coordination layer; MRMIC owns visual projection. This profile does not issue
an identity, decide continuity, activate a relation or contract, send a
message, or turn provider/runtime identifiers into an entity.

## Offline federated events (`eml-pmw`)

Federation v1 is provider-free and inventory-first. Each realm keeps its own
immutable event replica, exchanges only inventories and requested P0/P1 event
bytes, and records receiver observations separately from delivery, adoption,
authority, and authorship.

```text
event != delivery != observation != adoption != authority
replica sequence != global sequence
completed turn != adapter body available
```

Available commands are `event-create`, `event-inventory`, `event-diff`,
`event-import`, `event-reconcile`, `conflict-show`, `conflict-resolve`, and
`sync-status`. Ordinary tests and the two-realm acceptance scenario make no
network, provider, Wake, Bridge, or CTCL calls. The RAL adapter pins the
RAL-owned public schema by `$id`, commit, byte count, and SHA-256; it does not
vendor the schema or mutate a registry head.

## Same-database composition

`FabricJournal` tables use `pmw_` prefixes and can share the same SQLite file as the existing `eml_bridge` journal. This makes the Herdr runtime bridge an adapter/provider without destructive migration.

## Durable external wake (`eml-wake`)

`eml-wake` is a separate, file-first vertical slice for cross-dialogue when no
Claude recipient session is already awake. It claims one durable `wake_id`,
starts one **fresh** Claude worker, captures the host-observed provider session
ID and result, registers CTCL evidence, and commits an immutable ACK before any
optional notification.

```text
durable request
→ exclusive claim
→ fresh claude -p
→ provider result
→ CTCL registration
→ durable ACK
```

It deliberately does not resume, fork, or impersonate an existing interactive
AI. `target_kind=exact_instance` fails before provider launch. Version 1 accepts
only an explicitly authorized `generic_worker` or `line` request, with required
model, tools list, budget, timeout, payload digest, and authority reference.

### Source-checkout commands

```powershell
$env:PYTHONPATH = "src"
python -m eml_wake --root D:\path\to\wake-root --config D:\path\to\config.json create `
  --payload D:\path\to\payload.md `
  --sender agent://example/sender `
  --authority principal:example/cross-dialogue `
  --target-ref worker:claude:generic `
  --model claude-haiku-4-5-20251001 `
  --tools-policy no_tools
python -m eml_wake --root D:\path\to\wake-root --config D:\path\to\config.json submit D:\path\to\request.json
python -m eml_wake --root D:\path\to\wake-root --config D:\path\to\config.json run-once
python -m eml_wake --root D:\path\to\wake-root --config D:\path\to\config.json status wake:example:001
```

Examples are in `examples/wake/`. A continuous watchdog can be validated or
started with `scripts/Start-EmlWakeWatchdog.ps1`; the stop script verifies the
recorded PID's command line before stopping anything.

### Completion and identity boundary

```text
ACK committed to durable store != courier notified
fresh provider session != resident identity
fresh provider session != historical interactive instance
ai-NN route handle != durable reply address
request CTCL anchor != ACK CTCL anchor
```

CTCL HTTP registration is attempted once. If it is unavailable, the captured
provider result remains durable with explicit temporal degradation; Claude is
never replayed merely to obtain a timestamp.

## Local durable handoff (`eml-handoff`)

`eml-handoff` commits a shared P0/P1 document and immutable envelope before any
Bridge, queue, Monitor, or Wake notification is attempted. It does not start a
provider, does not wake an instance, and does not treat notification acceptance
as receiver acknowledgement.

```text
payload committed
→ envelope committed
→ optional notification
→ receiver claim
→ payload materialization
→ durable receipt or linked reply
```

Source-checkout example:

```powershell
$env:PYTHONPATH = "src"
python -m eml_handoff --root D:\path\to\handoff-root --config D:\path\to\config.json create `
  --payload D:\path\to\shared.md `
  --sender claim:sender `
  --sender-instance claim:instance `
  --target-kind task `
  --target-ref task:example `
  --authority principal:example/cross-dialogue
```

Portable examples are in `examples/handoff/`. The initial local deployment
allows only `shared_topic` and `task`; entity and exact-instance claims fail
closed unless a host-verifiable binding adapter is explicitly supplied.
