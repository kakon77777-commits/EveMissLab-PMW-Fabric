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

Planned work is tracked in [ROADMAP.md](ROADMAP.md). The canonical design for
the shared visual world is
[the Canvas-first integration contract](docs/architecture/Canvas_First_Integration_Contract_v0.1.md).
Security boundaries are documented in
[docs/security/SECURITY_BOUNDARIES.md](docs/security/SECURITY_BOUNDARIES.md),
and the portable wake procedure is in
[docs/operations/WAKE_QUICKSTART.md](docs/operations/WAKE_QUICKSTART.md).

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
└── adapters
    ├── Herdr Bridge importer
    ├── MRMIC Phase 12 HTTP projection
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

## Current MRMIC compatibility mode

MRMIC Phase 12 currently accepts typed Canvas objects including `frame`, but not `resource_portal`. The live HTTP adapter therefore supports:

```text
compat_frame_v0
```

This creates an existing `frame` Canvas object whose metadata carries the PMW resource reference. Once Phase 13 adds native `resource_portal`, use `native_resource_portal`.

Live external AI presence is deliberately refused against Phase 12 because the current WebSocket message's actor fields are data, not authenticated identity proof.

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
