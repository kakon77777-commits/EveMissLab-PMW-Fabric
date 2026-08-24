# Herdr–EveMissLab Bridge Protocol v0.1

## 0. Status

Version: `0.1`

Status: design specification + executable protocol-core reference.

Target Herdr source package: `herdr 0.8.0` from the uploaded `herdr-master.zip`.

This document defines the first stable boundary between a terminal/runtime multiplexer and a durable heterogeneous-agent communication system.

---

## 1. Problem statement

Herdr already provides the lower-level primitives required to operate heterogeneous coding agents:

- agent discovery and runtime identity;
- normalized agent lifecycle state;
- prompt submission;
- semantic waits;
- terminal reads;
- event subscriptions;
- process/session persistence and live handoff.

What Herdr does not attempt to define is a durable semantic conversation protocol between those agents.

The Bridge therefore solves a different problem:

$$
\boxed{
\mathrm{Runtime\ Coordination}
\not\equiv
\mathrm{Semantic\ Coordination}
}
$$

The Bridge MUST preserve this distinction.

---

## 2. Layer model

The complete EveMissLab stack is defined as:

$$
\boxed{
\mathrm{EML\ MultiAgent\ Runtime}
=
\mathrm{Herdr}
+
\mathrm{Bridge}
+
\mathrm{AI\ Board}
+
\mathrm{CTCL}
+
\mathrm{Durable\ Memory}
}
$$

with the following authority boundaries.

### 2.1 Herdr authority

Herdr is authoritative for current runtime coordinates and current observed agent state:

$$
R_a(t)=
(\mathrm{workspace},\mathrm{tab},\mathrm{pane},\mathrm{terminal},\mathrm{status}).
$$

### 2.2 Bridge authority

The Bridge is authoritative for:

- semantic identity binding;
- message/thread/correlation identity;
- delivery state;
- retry and uncertainty policy;
- cross-agent routing;
- loop prevention;
- semantic completion bookkeeping.

### 2.3 AI Board authority

AI Board is the canonical semantic communication space. A Herdr terminal prompt is a projection of a durable message, not the canonical message itself.

### 2.4 CTCL authority

CTCL is the canonical temporal/provenance coordinate. Herdr event sequence numbers are runtime-local evidence, not durable global time.

### 2.5 Durable Memory authority

Durable Memory stores long-horizon research state, summaries, artifacts, decisions, and references. It MUST NOT be reconstructed solely from terminal scrollback.

---

## 3. Core invariants

### I1 — Semantic identity is not a pane

A pane is a runtime coordinate. It is not a durable AI identity.

$$
\boxed{
I_{semantic}\neq I_{pane}
}
$$

A semantic agent MAY move to a new pane or reconnect to a native conversation while retaining the same semantic identity.

### I2 — Runtime settled is not task complete

Herdr status `idle` or `done` indicates a lifecycle condition, not proof that a delegated semantic task is complete.

$$
\boxed{
\mathrm{RuntimeSettled}
\not\Rightarrow
\mathrm{SemanticComplete}
}
$$

A delegation MUST have an explicit semantic completion record before the Bridge marks it `completed`.

### I3 — Herdr events are evidence, not canonical history

The uploaded Herdr source retains only the most recent 512 events in `EventHub`, and the sequence is process-local.

$$
\boxed{
\mathrm{HerdrEventSequence}
\neq
\mathrm{GlobalEventIdentity}
}
$$

The Bridge MUST durably journal relevant events as they arrive.

### I4 — Uncertain delivery is not retryable by default

If the transport disconnects after a prompt may have been submitted but before the Bridge knows the outcome, automatic re-prompting can duplicate work or actions.

$$
\boxed{
\mathrm{DeliveryUncertain}
\Rightarrow
\mathrm{ReconcileFirst}
}
$$

The Bridge MUST NOT blindly resend an uncertain prompt.

### I5 — Blocked state is a control boundary

A Herdr `blocked` state can represent an approval or question UI. Cross-agent automation MUST NOT translate `blocked` into automatic `send_keys` approval unless a separate explicit permission policy allows it.

### I6 — A runtime reply capture has confidence

Because Herdr explicitly does not track individual agent turns, every captured reply MUST carry one of:

$$
C\in\{\mathrm{structured},\mathrm{turn\_fenced},\mathrm{heuristic}\}.
$$

The Bridge MUST NOT silently upgrade heuristic capture to structured certainty.

---

## 4. Identity model

### 4.1 Semantic identity

A semantic identity is represented by a stable URI-like identifier:

```text
agent://evemisslab/<domain>/<name>
```

Examples:

```text
agent://evemisslab/research/claude-main
agent://evemisslab/research/codex-reviewer
agent://evemisslab/security/grok-auditor
```

Semantic identity describes the role/continuity used by the upper system.

### 4.2 Runtime binding

A semantic agent MAY have one active Herdr runtime binding:

$$
B_a=
(
\mathrm{runtime\_epoch},
\mathrm{HerdrSession},
\mathrm{AgentTarget},
\mathrm{AgentKind},
\mathrm{NativeSessionRef?},
\mathrm{WorkspaceId},
\mathrm{TabId},
\mathrm{PaneId},
\mathrm{TerminalId},
\mathrm{LaunchEpoch}
).
$$

`native_session_ref`, when available, is strong continuity evidence but MUST NOT replace the semantic identity.

### 4.3 Runtime epoch

Every successful Bridge connection/reconciliation to a Herdr server creates or resolves a `runtime_epoch_id`.

A new epoch MUST be created when the Bridge cannot prove continuity of the Herdr event sequence across a server replacement.

Therefore a Herdr event key is:

$$
E_H=(\mathrm{runtime\_epoch\_id},\mathrm{source\_sequence}).
$$

Never use `source_sequence` alone as a durable identifier.

---

## 5. Canonical message model

Every cross-agent message MUST be journaled before terminal projection.

The canonical path is:

$$
M
\rightarrow
\mathrm{AI\ Board/Journal}
\rightarrow
\mathrm{CTCL\ stamp}
\rightarrow
\mathrm{Herdr\ projection}.
$$

The reverse path is:

$$
\mathrm{AgentOutput}
\rightarrow
\mathrm{BridgeCapture}
\rightarrow
\mathrm{CanonicalReply}
\rightarrow
\mathrm{AI\ Board/CTCL}.
$$

### 5.1 Message identifiers

A message contains at least:

- `message_id` — globally unique within the Bridge store;
- `thread_id` — durable semantic discussion thread;
- `correlation_id` — logical task/operation correlation;
- `parent_message_id` — optional causal parent;
- sender semantic identity;
- one or more recipient semantic identities.

The model is a DAG, not a strict linked list:

$$
\mathrm{Thread}=G_M=(V_M,E_{reply}).
$$

This permits one message to fan out to multiple reviewers and later reconverge.

### 5.2 Route intent

`route_intent` is one of:

- `direct` — one semantic message directed to target agents;
- `reply` — causal reply to an earlier message;
- `delegate` — task assignment with delegation state;
- `broadcast` — publish to multiple semantic recipients;
- `notice` — informational; no automatic response implied.

An AI Board post MUST NOT automatically become a terminal prompt unless routing policy explicitly maps it to `direct`, `reply`, or `delegate` delivery.

---

## 6. Terminal projection frame

The canonical message is projected into the target agent's terminal through `agent.prompt`.

v0.1 defines a human-readable prompt frame:

```text
[EML-BRIDGE v0.1]
message_id: <message_id>
thread_id: <thread_id>
correlation_id: <correlation_id>
from: <semantic_agent_id>
route_intent: <intent>
reply_marker: <marker>

BEGIN_MESSAGE
<canonical payload text>
END_MESSAGE

When replying in this terminal, end the response with the exact reply_marker.
If the eml-bridge agent command is available, prefer a structured bridge reply instead.
[/EML-BRIDGE]
```

The frame is transport metadata, not the canonical stored message.

The reply marker MUST be unpredictable enough to avoid accidental collision with normal output.

---

## 7. Reply capture hierarchy

v0.1 defines three capture modes.

### 7.1 Structured capture

The target agent explicitly calls a future Bridge client/skill such as:

```text
eml-bridge reply <message_id> ...
```

or writes a canonical AI Board reply with the correct identifiers.

Confidence:

$$
C=\mathrm{structured}.
$$

This is the preferred mode.

### 7.2 Turn-fenced capture

The Bridge sends a unique `reply_marker`, waits for the target to enter an acceptable settled lifecycle state, reads terminal output, and finds the expected marker in the post-prompt response region.

Confidence:

$$
C=\mathrm{turn\_fenced}.
$$

### 7.3 Heuristic capture

If no structured reply or marker exists, the Bridge MAY read recent terminal output after a validated lifecycle transition and store it as a reply candidate.

Confidence:

$$
C=\mathrm{heuristic}.
$$

Heuristic capture MUST be visibly marked and MUST NOT trigger irreversible autonomous downstream actions without an additional policy decision.

---

## 8. Strict-turn delivery algorithm

Herdr permits prompting an agent that is already working, and `agent.prompt --wait` does not identify individual turns. Therefore Bridge strict mode imposes an additional gate.

### 8.1 Preconditions

For `strict_turn=true`:

1. resolve semantic identity to one live runtime binding;
2. obtain current `AgentInfo`;
3. verify target identity and terminal identity;
4. require a settled status before submission:

$$
S_{pre}\in\{\mathrm{idle},\mathrm{done}\};
$$

5. if `working`, wait for settlement first;
6. if `blocked`, do not prompt;
7. if `unknown`, defer unless policy explicitly permits uncertain state delivery.

### 8.2 Submission fence

Before prompt submission the Bridge records:

$$
F_0=(\mathrm{terminal\_id},\mathrm{state\_change\_seq},\mathrm{revision},\mathrm{runtime\_epoch}).
$$

Then it submits the framed message using `agent.prompt` with a wait for accepted settled states.

### 8.3 Postcondition

After the prompt returns, the Bridge verifies:

- the target still resolves to the same terminal occupant;
- the runtime epoch is unchanged;
- an appropriate lifecycle transition occurred;
- the target is settled or blocked;
- captured output confidence is recorded.

If target identity changes during the operation, the delivery MUST fail as `target_replaced` rather than attributing output to the replacement agent.

---

## 9. Delivery state machine

A message projection has the following durable states:

```text
journaled
  -> resolving_target
  -> ready
  -> prompt_submitted
  -> activity_observed
  -> runtime_settled
  -> reply_captured
  -> acknowledged
```

Exceptional branches:

```text
resolving_target -> target_unavailable
ready            -> blocked
ready            -> suppressed
prompt_submitted -> uncertain
activity_observed-> uncertain
runtime_settled  -> capture_failed
*                -> failed
```

The Bridge MUST persist each externally meaningful transition before taking the next non-idempotent action.

### 9.1 Exactly-once is not claimed

v0.1 explicitly does not claim exactly-once terminal prompt semantics.

The practical guarantee is:

- durable journal operations are idempotent by `idempotency_key`;
- a known-failed pre-submit operation MAY be retried;
- a known-submitted prompt MUST NOT be automatically submitted again;
- an unknown submission outcome becomes `uncertain`.

---

## 10. Delegation protocol

Delegation is not equivalent to messaging.

A delegation has:

- `delegation_id`;
- issuer;
- assignee;
- task message;
- constraints;
- expected outputs;
- semantic status.

Delegation state is:

$$
D\in\{
\mathrm{proposed},
\mathrm{accepted},
\mathrm{running},
\mathrm{blocked},
\mathrm{completed},
\mathrm{failed},
\mathrm{cancelled}
\}.
$$

A Herdr transition to `done` MAY update runtime evidence, but MUST NOT directly set:

$$
D=\mathrm{completed}.
$$

Completion requires one of:

1. a structured semantic reply declaring completion;
2. an accepted artifact record tied to the delegation;
3. an upper-layer verifier explicitly marking completion.

---

## 11. Loop prevention

Cross-agent systems can accidentally construct positive feedback loops.

v0.1 requires all automatic routing to carry:

- `hop_count`;
- `max_hops`;
- `auto_reply_depth`;
- `route_trace`;
- `payload_hash`;
- `idempotency_key`.

### 11.1 Hard hop bound

The default is:

$$
H_{max}=8.
$$

When:

$$
H\ge H_{max},
$$

the Bridge MUST suppress further automatic routing.

### 11.2 Automatic reply bound

Default:

$$
A_{max}=6.
$$

This bound applies only to automatically generated reply chains. Human-authored continuation MAY open a new automatic budget.

### 11.3 Duplicate suppression

The Bridge SHOULD suppress a repeated automatic route when the tuple

$$
(
\mathrm{sender},
\mathrm{recipient},
\mathrm{thread},
\mathrm{payload\_hash}
)
$$

has already been delivered within the configured deduplication window.

### 11.4 Board echo rule

A message published to AI Board MUST carry an origin marker. The Bridge MUST NOT consume its own mirrored post and route it back into the same terminal as a new message.

---

## 12. Runtime event normalization

Herdr runtime events MUST be transformed into durable Bridge events.

A normalized event includes:

```json
{
  "event_id": "evt_...",
  "runtime_epoch_id": "hep_...",
  "source": "herdr",
  "source_sequence": 123,
  "event_type": "pane.agent_status_changed",
  "runtime_binding_id": "bind_...",
  "observed_at": "...",
  "recorded_at": "...",
  "ctcl_ref": "...",
  "raw_hash": "sha256:..."
}
```

`source_sequence` MUST only be interpreted within `runtime_epoch_id`.

---

## 13. Handoff/restart recovery

Herdr live handoff preserves long-lived process/session state when successful, but does not preserve transient waits, subscriptions, client sockets, or in-flight requests.

Therefore the Bridge recovery procedure is mandatory.

### 13.1 On disconnect

The Bridge MUST:

1. stop new prompt submissions;
2. close the current subscription epoch;
3. mark in-flight operations according to their last durable delivery state;
4. mark any operation at or after `prompt_submitted` but before durable capture as `uncertain` unless the outcome is otherwise provable.

### 13.2 On reconnect

The Bridge MUST:

1. establish a new or reconciled `runtime_epoch_id`;
2. obtain a fresh session snapshot / agent list;
3. rebind semantic identities;
4. resubscribe to runtime events;
5. reconcile uncertain operations;
6. only then resume new prompt submission.

### 13.3 Reconciliation

For an uncertain prompt the Bridge SHOULD inspect:

- whether the original terminal/session still exists;
- native session continuity;
- current `state_change_seq` and revision;
- recent output for the reply fence;
- AI Board for an already-structured reply.

If evidence remains ambiguous, state stays `uncertain` and MUST NOT be converted into an automatic resend.

---

## 14. Permission and governance boundary

v0.1 defines separate capabilities:

- `message` — send semantic messages;
- `delegate` — assign tasks;
- `spawn` — start a new Herdr agent;
- `focus` — change terminal focus;
- `send_keys` — raw logical key injection;
- `approve_blocked` — answer recognized approval/question UIs;
- `filesystem_artifact` — publish artifact references;
- `external_network` — authorize network-affecting tasks at the upper policy layer.

Recommended default:

```text
message          allow
reply            allow
delegate         policy-dependent
spawn            policy-dependent
focus            allow-local-only
send_keys        deny-cross-agent
authorize_blocked deny
auto-approve     deny
```

The Bridge MUST NOT infer approval authority from the fact that an agent can technically call Herdr.

---

## 15. Trust model

Every payload carries a trust label:

- `system` — generated by the trusted bridge control plane;
- `internal` — authored by a known internal human/agent;
- `external` — obtained from external content;
- `untrusted` — explicitly untrusted data.

Trust is provenance metadata, not a claim that the content is true.

An agent message that embeds external material SHOULD preserve the external/untrusted label instead of laundering it into `internal` merely because another AI quoted it.

---

## 16. Proposed Bridge local API

The exact transport MAY be JSON-lines, HTTP, local socket RPC, or a plugin connector. v0.1 standardizes semantic operation names:

```text
bridge.agent.bind
bridge.agent.resolve
bridge.agent.list
bridge.message.send
bridge.message.reply
bridge.message.get
bridge.thread.get
bridge.thread.list
bridge.delegation.create
bridge.delegation.update
bridge.delegation.get
bridge.runtime.reconcile
bridge.event.subscribe
```

These are Bridge methods, not Herdr methods.

The Bridge adapter maps lower operations to Herdr primitives such as:

```text
agent.get
agent.prompt
agent.wait
agent.read
agent.start
events.subscribe
session.snapshot
```

---

## 17. Claude ↔ Codex canonical workflow

Let:

$$
C=\text{Claude Code semantic agent},
$$

$$
G=\text{Codex semantic agent}.
$$

A strict review request is:

$$
C
\xrightarrow{M_1}
\mathrm{BridgeJournal}
\xrightarrow{\mathrm{resolve}(G)}
\mathrm{Herdr}
\xrightarrow{\mathrm{prompt}}
G.
$$

After validated runtime settlement:

$$
G
\xrightarrow{R_1}
\mathrm{BridgeCapture}
\xrightarrow{\mathrm{AI\ Board+CTCL}}
C.
$$

If Codex emits a structured Bridge reply, the terminal read is supporting evidence rather than the canonical semantic reply.

---

## 18. v0.1 implementation phases

### Phase A — observation + durable identity

- connect to Herdr;
- discover Claude/Codex;
- bind semantic IDs;
- persist event stream;
- no autonomous cross-agent prompt yet.

### Phase B — strict direct messages

- canonical message journal;
- strict-turn gate;
- prompt frame;
- turn-fenced capture;
- AI Board publication.

### Phase C — structured agent skill

- give agents `eml-bridge send/reply/delegate` primitives;
- structured replies become default;
- heuristic capture becomes fallback only.

### Phase D — CTCL + recovery hardening

- full CTCL stamping;
- runtime epoch reconciliation;
- handoff/restart uncertainty tests;
- durable outbox/inbox.

### Phase E — bounded autonomy

Only after the previous phases pass fault-injection tests:

- automatic reviewer routing;
- delegation graph;
- multi-agent research loops;
- policy-controlled spawning.

---

## 19. Non-goals of v0.1

v0.1 does not claim:

- exactly-once terminal delivery;
- perfect semantic turn segmentation from terminal output;
- proof that Herdr's inferred agent state equals the agent's internal cognitive state;
- safe autonomous approval of permission dialogs;
- cross-machine consensus;
- cryptographic identity for agents;
- a replacement for AI Board, CTCL, or durable research memory.

---

## 20. Acceptance criteria

Bridge v0.1 is considered implemented when all of the following are demonstrated:

1. Claude Code and Codex have stable semantic IDs independent of pane IDs.
2. A Claude-to-Codex message is durably journaled before prompt projection.
3. Strict mode refuses to send to `blocked` and waits out `working`.
4. A Codex reply is captured with explicit confidence classification.
5. A reply is published with the original `thread_id` and `correlation_id`.
6. Event records survive Bridge/Herdr restart in the durable store.
7. A Herdr handoff during prompt execution produces `uncertain` rather than a blind duplicate prompt.
8. Loop guards suppress a synthetic self-amplifying agent loop.
9. `send_keys`/approval is denied by default to automated cross-agent traffic.
10. The entire protocol can run without patching Herdr core.

The resulting architecture is therefore:

$$
\boxed{
\mathrm{Herdr\ Runtime\ Truth}
\rightarrow
\mathrm{Bridge\ Reliability}
\rightarrow
\mathrm{AI\ Board\ Semantics}
\rightarrow
\mathrm{CTCL\ Provenance}
\rightarrow
\mathrm{Durable\ Research\ Memory}
}
$$
