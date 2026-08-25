# EveMissLab PMW Fabric Roadmap

This roadmap separates verified software from architectural direction.

> Roadmap entries are non-claims until executable code, tests, and review
> evidence land in the repository.

## 1. Verified foundation

Implemented in the initial public repository:

- provider-neutral PMW workspace, task, resource-binding, presence, decision,
  and provenance semantics;
- a Canvas-first object model and deterministic mock visual adapter;
- a Herdr Bridge adapter with message framing, journaled delivery, structured
  reply capture, and target authority locks;
- a durable file-first external wake path that starts one fresh Claude worker;
- required model, tools, permission, budget, timeout, authority, and payload
  digest contracts;
- receiver-side `wake_id` idempotency and immutable ACK publication;
- CTCL request and ACK evidence without automatic replay when time evidence is
  unavailable;
- explicit refusal to impersonate or resume a historical resident instance.
- **Local Durable Handoff Mailbox v0.1**: provider-free outbox-first P0/P1
  documents, immutable claim/materialization/receipt state, and duplicate
  delivery protection.

## 2. Canvas integration

Next, connect PMW semantics to a live MRMIC/NVCL infinite logical Canvas:

- ARCP–PMW–MRMIC Integration Profile v1 contract pinning and negotiation;

- viewport-based unbounded workspace rendering;
- typed `resource_portal` projections;
- snapshot and governed live-surface modes;
- explicit ownership boundaries between Canvas geometry and provider state;
- revision, idempotency, and conflict gates for multi-agent operations.

## 3. Shared collaboration

Build the actual shared work area beyond text relay:

- multi-human and multi-AI presence, cursors, selections, and task focus;
- task, document, browser, terminal, code, discussion, and artifact surfaces;
- governed handoff gestures backed by authority records;
- causal views linking messages, actions, evidence, decisions, and outputs;
- structured-first observation with visual regions when spatial appearance is
  material to the task.

## 4. Advanced shared world

Longer-term research and product direction:

- provider federation without identity collapse;
- richer multimodal and spatial workflows;
- policy-governed shared tools and action surfaces;
- branch, isolate, join, and reconciliation workflows appropriate to each
  provider and resource type;
- durable cross-provider projects that continue without a human acting as the
  message courier.

The advanced world does not imply token exchange, hidden-context transfer,
automatic resident continuity, or universal conflict merging.
