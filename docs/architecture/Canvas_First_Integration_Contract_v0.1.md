# EveMissLab Canvas-First Integration Contract v0.1

**Status:** Draft canonical integration contract
**Date:** 2026-08-15
**Primary architectural decision:** MRMIC Canvas is the primary visual world; Tandem Browser, Herdr runtime, AI Board, code/artifact providers, documents, images and other tools are projected into that world as resource surfaces.
**Scope:** PMW Workspace Fabric ↔ MRMIC/NVCL ↔ Tandem ↔ Herdr ↔ AI Board ↔ CTCL
**Canonical source:** UTF-8 Markdown, this file.

## 0. Source anchors

This contract is grounded against the following repository states:

- `kakon77777-commits/MRMIC_NVCL` — `main@6606b54532c0f327206e7c021120370044b6e0ff`
- `kakon77777-commits/tandem-browser` — PR #2 branch `pmw-mainline/join-authority-i4@0628a03d7e0bec5f5a081ae64739418d9a320129`
- `herdrdev/herdr` — `master@9e6c2b4e0957498b7da884ed2789fe28b9cde9cf`

The systems remain independently evolvable providers. They do not need one repository, one process, one programming language or one persistence backend.

---

## 1. Architectural decision

The workbench is **canvas-first**, not browser-first and not terminal-first.

The canonical decomposition is

$$
\mathcal W
=
P_{\mathrm{PMW}}
\oplus
P_{\mathrm{Visual}}
\oplus
P_{\mathrm{Runtime}}
\oplus
P_{\mathrm{Semantic}}
\oplus
P_{\mathrm{Temporal}}.
$$

Where

$$
P_{\mathrm{PMW}}
=
\text{identity}
+
\text{task}
+
\text{logical workspace}
+
\text{resource binding}
+
\text{authority}
+
\text{handoff}
+
\text{decision receipt},
$$

$$
P_{\mathrm{Visual}}
=
\text{MRMIC Canvas},
$$

$$
P_{\mathrm{Runtime}}
=
\text{Herdr + runtime agents},
$$

$$
P_{\mathrm{Semantic}}
=
\text{AI Board and other discussion/memory surfaces},
$$

and

$$
P_{\mathrm{Temporal}}
=
\text{CTCL / provenance}.
$$

Tandem is not the root workbench container. Tandem is a resource provider whose browser tabs, browser workspaces, browser state trees, annotations and browser-specific handoffs can be projected into the visual world.

The primary containment relation is

$$
\boxed{
\text{PMW Logical Workspace}
\rightarrow
\text{MRMIC Canvas}
\rightarrow
\text{Resource Surfaces}
}
$$

rather than

$$
\text{Browser}
\rightarrow
\text{Canvas}.
$$

---

## 2. Non-goals

This contract does not:

1. merge the MRMIC, Tandem, Herdr, AI Board or CTCL codebases;
2. require a universal CRDT for every state conflict;
3. treat screenshots as canonical browser state;
4. treat Herdr pane IDs as permanent AI identities;
5. treat Canvas objects as canonical copies of external resources;
6. allow an AI to self-assert human identity or authority;
7. require all resource surfaces to be live at all times;
8. define a universal semantic merge for Browser JOIN, code merge and reasoning synthesis.

Each provider retains authority over the state it actually owns.

---

## 3. Canonical object model

### 3.1 PMW logical workspace

A PMW logical workspace is the cross-provider collaboration container.

$$
W_P
\neq
W_M
\neq
W_T
\neq
W_H
$$

where $W_P$ is the PMW logical workspace, $W_M$ the MRMIC workspace/canvas namespace, $W_T$ a Tandem browser workspace, and $W_H$ a Herdr runtime workspace.

The binding is one-to-many:

$$
W_P
\rightarrow
\left\{
W_M,
W_T^{(1)},\ldots,
W_H^{(1)},\ldots
\right\}.
$$

A PMW workspace MUST have a stable `pmwWorkspaceId`. Provider-local IDs MUST be stored as bindings, never substituted as the canonical workspace ID.

### 3.2 Agent identity

The canonical AI/user identity is a PMW semantic identity.

$$
I_P
\neq
I_{\mathrm{HerdrPane}}
\neq
I_{\mathrm{HerdrNativeSession}}
\neq
I_{\mathrm{TandemAuth}}
\neq
I_{\mathrm{CanvasClient}}.
$$

A semantic agent has one canonical ID and zero or more authenticated provider bindings.

```json
{
  "semanticAgentId": "agent:claude-main",
  "kind": "ai",
  "bindings": [
    {
      "provider": "herdr",
      "bindingType": "agent_session",
      "providerResourceId": "claude-main",
      "nativeSessionId": "claude-session-...",
      "verified": true
    },
    {
      "provider": "tandem",
      "bindingType": "authenticated_actor",
      "providerResourceId": "agent:82f2a910",
      "verified": true
    }
  ]
}
```

A caller-supplied free-text `actorId` MUST NOT be sufficient to claim an existing semantic identity.

The trusted resolution path is

$$
\text{Authenticated Principal}
\rightarrow
\text{Provider Binding}
\rightarrow
\text{Semantic Agent Identity}.
$$

### 3.3 PMW task

A PMW task is cross-provider. It MAY bind to a Tandem `AITask`, one or more Herdr agents, an AI Board thread, Canvas objects, GitHub resources and CTCL provenance.

$$
T_P
\rightarrow
\mathcal P(R).
$$

A provider-local task remains valid inside its provider but is not automatically the global task ID.

---

## 4. Canvas as the Visual World Plane

### 4.1 Logical infinity

The root Canvas SHOULD be treated as an unbounded logical two-dimensional space.

$$
C_{\infty}
\cong
\mathbb R^2
$$

at the conceptual level.

Implementation MUST NOT allocate an infinite raster. Rendering remains viewport-based.

A view is

$$
V_a(t)
=
(x,y,w,h,z)
$$

for actor $a$ at time $t$.

### 4.2 Canvas canonical state

MRMIC typed objects, transactions, revisions, event hashes and state-vector synchronization remain the canonical state for Canvas-native objects.

Canvas-native objects include text, shapes, images, freehand marks, frames, groups, `agent_note`, `subcanvas`, and future relations that are truly owned by Canvas.

External resource portals are different: Canvas owns their **projection geometry and visual metadata**, while the provider owns the resource itself.

---

## 5. Resource portal model

### 5.1 Definition

A `resource_portal` is a Canvas object that projects an external resource into the shared visual world.

$$
\pi_C:
R
\rightarrow
O_C.
$$

The Canvas object is not the resource:

$$
\pi_C(r)
\neq
r.
$$

### 5.2 Required portal fields

Every resource portal MUST identify provider, resource kind, provider resource ID, display mode, projection state, canonical PMW workspace, optional PMW task, authority/interaction policy and visual transform.

Representative metadata:

```json
{
  "provider": "tandem",
  "resourceKind": "browser_tab",
  "providerResourceId": "tab-17",
  "displayMode": "snapshot",
  "interactionMode": "inspect",
  "pmwWorkspaceId": "pmw-ws-research-001",
  "pmwTaskId": "pmw-task-001"
}
```

### 5.3 Initial resource kinds

v0.1 recognizes `browser_tab`, `browser_workspace`, `browser_state_node`, `terminal_agent`, `terminal_pane`, `ai_board_thread`, `code_diff`, `document`, `image`, `video`, `artifact` and `external_generic`.

The list is extensible. Provider semantics remain provider-specific.

---

## 6. Tandem Browser projection

### 6.1 Ownership split

For a browser portal, Canvas owns

$$
G_B
=
(x,y,w,h,z,\text{portal metadata})
$$

while Tandem owns

$$
S_B
=
(\text{URL},\text{WebContents},\text{session},\text{DOM},\text{network},\text{browser history},\text{browser state tree}).
$$

Canvas MUST NOT silently replace Tandem browser state with screenshot state.

### 6.2 Snapshot/live dual mode

Browser portals have at least two render modes:

```text
snapshot
live
```

Snapshot mode displays a provider-produced current preview. Live mode mounts the real interactive browser surface through a host overlay.

$$
S_B^{\mathrm{snapshot}}
\xrightarrow{\mathrm{activate}}
S_B^{\mathrm{live}}.
$$

A live browser surface SHOULD use an HTML/Electron overlay coordinated with Canvas world coordinates rather than embedding Electron `<webview>` directly inside SVG.

### 6.3 Focus and visibility must separate

The new browser surface state is

$$
B_s
=
(
\text{mounted},
\text{visible},
\text{focused},
\text{owner},
\text{mode}
).
$$

Therefore

$$
\boxed{
\text{Focused}
\neq
\text{Visible}.
}
$$

Multiple browser portals MAY be visible simultaneously.

The implementation MAY impose a live-surface budget

$$
N_{\mathrm{live}}
\leq
k
$$

while additional portals remain snapshot projections.

### 6.4 Browser ISOLATE

Tandem's tab ownership/lock mechanism remains the browser-specific implementation of PMW `ISOLATE`.

Canvas display does not transfer browser ownership. Selecting a portal is not automatically controlling it.

---

## 7. Herdr runtime projection

Herdr remains the runtime grounding source for terminal agents.

$$
R_H
=
(
\text{agent kind},
\text{native session},
\text{pane},
\text{workspace},
\text{status},
\text{state change sequence}
).
$$

Canvas may project this as an `agent` or `terminal_agent` portal containing semantic agent name, runtime state, task assignment, optional terminal preview, and PMW-authorized interaction controls.

The Canvas MUST NOT become the canonical process manager.

$$
\text{Herdr}
\rightarrow
\text{PMW Fabric}
\rightarrow
\text{Canvas Projection}.
$$

Dragging a task card onto an agent MAY be interpreted as a PMW HANDOFF/delegation request, but the visual gesture itself is only intent. PMW authority/routing decides whether it is legal; Herdr performs runtime delivery.

---

## 8. AI Board projection

AI Board remains the canonical semantic/discussion system.

A Canvas AI Board portal is

$$
\pi_C(
\text{AI Board thread}
)
$$

and MAY show recent messages, thread state, participants, unresolved decisions, artifact links and task/handoff references.

Canvas annotations do not silently rewrite canonical AI Board messages.

A Canvas action that creates an AI Board message must route through the AI Board adapter and record provenance.

---

## 9. Shared presence

Presence is a first-class cross-agent visual state.

$$
P_a
=
(
I_a,
V_a,
c_a,
S_a,
T_a,
t
)
$$

where $I_a$ is semantic identity, $V_a$ viewport, $c_a$ cursor, $S_a$ selected object IDs, $T_a$ current task/activity label and $t$ timestamp.

Presence is ephemeral. It MUST NOT be confused with durable object state.

The PMW Fabric SHOULD map provider sessions to semantic identity before exposing presence to peers.

Multiple AI agents and humans may simultaneously occupy the same Canvas room.

---

## 10. Multimodal observation contract

### 10.1 Three observation channels

An agent may observe the shared visual world through

$$
O_a
=
O_{\mathrm{structured}}
\oplus
O_{\mathrm{visual}}
\oplus
O_{\mathrm{presence}}.
$$

`structured` contains typed Canvas objects, resource metadata, revisions and provider summaries.

`visual` contains SVG/PNG/ROI or another rendered representation.

`presence` contains peer cursor/viewport/selection/task state.

### 10.2 Structured-first principle

When a task can be solved from typed state, the system SHOULD avoid unnecessary raster delivery.

Raster/multimodal observation is used when spatial appearance, visual ambiguity or provider output requires it.

### 10.3 Visual freshness

A visual action MAY require a freshness/transition gate.

$$
A
=
f(
O_t,
\operatorname{revision}(C_t),
\operatorname{frameId}
).
$$

An agent MUST NOT assume a previous visual observation still describes the shared state after conflicting updates.

---

## 11. Canvas transaction and multi-agent concurrency

Canvas collaboration is not universal automatic conflict merging.

$$
\text{State Vector}
+
\text{Ordered Updates}
+
\text{Revision Preconditions}
+
\text{Idempotency}
+
\text{Explicit Conflict}.
$$

A concurrent incompatible operation may fail with a revision/precondition conflict. This is intentional.

$$
\text{Claude.move}(O)
\parallel
\text{Codex.delete}(O)
$$

need not be automatically merged.

Conflict resolution can invoke `ISOLATE`, CAS/retry, branch/proposal mode, HANDOFF, provider-specific JOIN, human authority or a decision receipt.

---

## 12. JOIN semantics

`JOIN` is an abstract PMW operator with provider-specific semantics.

There is no universal implementation

$$
J(x,y)
$$

that is correct for every resource type.

$$
J_{\mathrm{browser}}
=
\text{Tandem State Tree JOIN},
$$

$$
J_{\mathrm{code}}
=
\text{Git merge/rebase/cherry-pick or a governed synthesis},
$$

$$
J_{\mathrm{reasoning}}
=
\text{synthesis/reconciliation via AI Board or a designated agent}.
$$

A Canvas visual connection between two branches is not itself a semantic merge.

---

## 13. Authority

The system-wide authority invariant is

$$
\boxed{
\text{An AI must not autonomously cross a human-required authority boundary.}
}
$$

Provider-specific examples:

- Herdr: an agent blocked on approval/question must not be auto-cleared by arbitrary cross-agent key injection.
- Tandem: medium/high-risk browser handoffs cannot be self-cleared by an AI actor when human authority is required.
- Canvas: a visual gesture cannot forge another identity or bypass provider permission.
- AI Board: future approval gates must preserve the same authority direction.

Authority checks occur before the side effect, not merely in the UI.

---

## 14. Decision receipts

Transport state and decision state are distinct axes.

Delivery state may include `queued`, `submitted`, `activity_observed`, `settled`, `reply_captured`, `uncertain`, `failed`.

Decision state uses `ACK`, `NO_ACTION`, `ACTION`, `ERROR`.

Therefore

$$
\text{reply\_captured}
\not\Rightarrow
\text{ACTION}.
$$

A decision receipt SHOULD include semantic actor ID, PMW task/workspace, provider/resource references, decision, risk, evidence references, provenance timestamp and optional note.

Decision receipts are append-only semantic records.

---

## 15. CTCL / provenance

Every durable cross-provider mutation SHOULD produce a provenance envelope.

$$
Q
=
(
\text{eventId},
\text{actor},
\text{workspace},
\text{task},
\text{provider},
\text{resource},
\text{operation},
t,
\text{evidenceRefs}
).
$$

CTCL does not replace provider-native event logs. It links them.

The provenance graph should answer who acted, on what, in which PMW task/workspace, through which provider, based on which evidence, and what state or artifact resulted.

---

## 16. Canonical resource binding

The PMW Fabric stores resource bindings.

A binding MUST include:

```text
bindingId
pmwWorkspaceId
provider
resourceKind
providerResourceId
semanticAgentId?
pmwTaskId?
canvasObjectId?
createdAt
updatedAt
```

Bindings make resource identity explicit.

String similarity or display labels MUST NOT be used as the primary identity reconciliation mechanism.

---

## 17. Projection lifecycle

Every projected external resource follows:

```text
UNBOUND
  ↓
BOUND
  ↓
PROJECTED_SNAPSHOT
  ↓
PROJECTED_LIVE
  ↓
SUSPENDED
  ↓
CLOSED
```

Provider resource death and Canvas object deletion are distinct.

Deleting a portal SHOULD default to deleting the projection, not destroying the provider resource, unless authority policy explicitly chooses a destructive action.

---

## 18. Suggested v0.1 data-plane split

```text
PMW Fabric
├── AgentBindingRegistry
├── PMWTaskRegistry
├── PMWWorkspaceRegistry
├── ResourceBindingRegistry
├── AuthorityEngine
├── DecisionReceiptLog
├── ProvenanceEmitter
└── AdapterRouter
    ├── MRMIC adapter
    ├── Tandem adapter
    ├── Herdr adapter
    ├── AI Board adapter
    └── CTCL adapter
```

MRMIC owns CanvasStore, StateVectorSync, Presence, visual observation, `resource_portal` projections and the live-overlay host.

Tandem owns Tabs/WebContents, browser workspaces, tab locks, State Tree, browser tasks, browser handoffs and MCP/API.

Herdr owns agent lifecycle, PTY/process, prompt/wait/read, sessions and runtime events.

---

## 19. Minimal integration hooks

### 19.1 MRMIC

Required first additions:

1. add `resource_portal` as a Canvas object type or equivalent provider-neutral projection object;
2. allow authenticated `agent` presence, not only browser UI `user` presence;
3. add a portal registry/view model separating Canvas geometry from provider state;
4. add live overlay transform hooks;
5. expose provider/resource references through structured observation;
6. preserve revision/precondition/idempotency semantics.

### 19.2 Tandem

Required first additions:

1. expose stable provider resource descriptors for tabs/workspaces/state nodes;
2. separate `focused` from `visible`;
3. support multiple visible browser surfaces or an explicit live-surface budget;
4. add a safe preview/snapshot endpoint for Canvas projection;
5. accept PMW binding metadata through trusted configuration/pairing, not arbitrary identity headers;
6. preserve tab lock, handoff, risk and authority semantics.

### 19.3 Herdr Bridge / PMW Fabric

Required first additions:

1. expand the runtime bridge into a provider adapter under PMW Fabric;
2. add `agent_bindings`;
3. add `pmw_tasks`;
4. add `pmw_workspaces`;
5. add `resource_bindings`;
6. add normalized presence routing;
7. add Canvas projection events;
8. preserve strict-turn, uncertain-delivery and blocked-authority rules.

---

## 20. First integrated end-to-end scenario

The first acceptance scenario should be deliberately small.

Actors:

- `user:neo`
- `agent:claude-main`
- `agent:codex-reviewer`

One PMW workspace contains one MRMIC root Canvas.

Resources:

- one Claude Herdr agent portal;
- one Codex Herdr agent portal;
- two Tandem browser tab portals;
- one AI Board thread portal;
- one Canvas-native note;
- one decision receipt projection.

Flow:

1. Neo enters the PMW workspace.
2. Claude and Codex appear as authenticated presences on the same Canvas.
3. Claude receives a research task.
4. Claude activates Browser Portal A and gathers evidence.
5. Claude creates an `agent_note` containing a structured hypothesis.
6. Claude delegates independent verification to Codex through PMW Fabric/Herdr.
7. Codex activates Browser Portal B without stealing Browser Portal A ownership.
8. Codex adds its own note/evidence.
9. Browser branches may be compared and, where appropriate, reconciled through Tandem's provider-specific JOIN.
10. A synthesis step records `ACK`, `NO_ACTION`, `ACTION` or `ERROR`.
11. AI Board receives the durable discussion/synthesis record.
12. CTCL links runtime delivery, browser evidence, Canvas objects and the semantic decision.

The scenario passes only if the same semantic agent identities are preserved across Herdr, Tandem, Canvas and AI Board bindings.

---

## 21. Acceptance invariants

### A1 — Canonical Identity

One semantic agent remains one identity across provider bindings.

### A2 — No Identity Forgery

A caller cannot become `user` or another agent merely by supplying a free-text actor ID.

### A3 — Projection Is Not Ownership

Deleting/moving a portal does not silently destroy or rewrite provider-native state.

### A4 — Browser Focus/Visibility Separation

At least two browser portals can be visible without forcing both to be focused.

### A5 — Shared Presence

Two AI agents and one human can simultaneously expose distinct presence in one Canvas room.

### A6 — Visual/Structured Dual Observation

An agent can inspect typed state without a raster call and request visual evidence when required.

### A7 — Conflict Is Explicit

Conflicting object revisions fail or branch rather than silently last-write-winning.

### A8 — Human Authority Boundary

An AI cannot visually or programmatically bypass a human-required approval.

### A9 — Durable Decision Receipt

A real decision point creates an append-only receipt.

### A10 — Provenance Linkage

A final decision can trace back to relevant runtime delivery, Canvas state and external evidence.

---

## 22. Implementation order

$$
\text{Identity}
\rightarrow
\text{Resource Binding}
\rightarrow
\text{Canvas Portal}
\rightarrow
\text{Presence}
\rightarrow
\text{Browser Live Overlay}
\rightarrow
\text{Herdr Agent Projection}
\rightarrow
\text{Decision/Provenance}
\rightarrow
\text{AI Board}.
$$

Do not start with a large UI redesign. First prove the cross-provider identity and resource graph, then enrich the visual shell.

---

## 23. Naming decision

Until a final product name is chosen, use neutral layer names:

- **EveMissLab PMW Fabric** — cross-provider collaboration state;
- **MRMIC Visual World** — Canvas state and visual interaction;
- **Tandem Browser Provider** — browser capabilities;
- **Herdr Runtime Provider** — terminal/agent runtime capabilities;
- **AI Board Semantic Provider** — discussion/shared cognition;
- **CTCL Provenance Provider** — temporal/provenance linkage.

The user-facing application may later be named independently of any provider.

---

## 24. Final principle

The system is not a browser with AI added, and not a whiteboard with plugins added.

Its intended abstraction is

$$
\boxed{
\text{Shared Visual Computational World}
}
$$

in which humans and heterogeneous AI agents occupy one logical workspace, share a visual/spatial world, use provider-specific tools, exchange semantic information, preserve explicit authority boundaries and leave durable provenance.

The Canvas is the visible world.

The PMW Fabric is the coordination law.

Herdr grounds runtime existence.

Tandem provides browser capability.

AI Board carries durable semantic collaboration.

CTCL links the history of the whole system.
