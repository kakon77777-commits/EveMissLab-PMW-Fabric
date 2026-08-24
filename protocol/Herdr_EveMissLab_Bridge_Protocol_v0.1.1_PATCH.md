# Herdr-EveMissLab Bridge Protocol v0.1.1 Patch

Status: implementation-driven patch over v0.1.

This patch does not replace the complete v0.1 document. It corrects three runtime semantics discovered while implementing the first executable bridge.

## 1. Submission is a two-stage durable operation

Protocol v0.1 described strict submission as `agent.prompt` with an integrated wait. The runtime implementation uses a stronger durability boundary:

```text
persist READY + runtime fence
-> agent.prompt without wait
-> on confirmed return, persist PROMPT_SUBMITTED
-> observe prompt effect
-> persist ACTIVITY_OBSERVED
-> agent.wait for settled state when necessary
-> persist RUNTIME_SETTLED or BLOCKED
```

The reason is crash ambiguity. A combined prompt-and-wait call may keep the client blocked after the prompt has already been accepted. If the client disappears during that interval, the bridge cannot durably distinguish "not submitted" from "submitted but not yet settled".

The two-stage procedure gives the bridge a durable boundary immediately after Herdr confirms prompt submission.

Let the pre-submission runtime fence be

$$
F_0=(T_0,S_0,R_0,E_0),
$$

where $T_0$ is `terminal_id`, $S_0$ is `state_change_seq`, $R_0$ is `revision`, and $E_0$ is the bridge runtime epoch.

Prompt effect is considered observed only when the live target remains identity-compatible and either

$$
S_1>S_0
$$

or an accepted lifecycle transition away from the pre-submission state is observed.

Failure to observe prompt effect does not imply safe retry.

## 2. Submission ambiguity is reachable from READY

A transport failure can happen after the bridge starts `agent.prompt` but before it receives Herdr's response. Therefore the durable state graph MUST include

```text
ready -> uncertain
```

when the transport cannot prove that submission did not occur.

The bridge MUST NOT automatically resend from `uncertain`.

## 3. BLOCKED is reachable after submission

Herdr `blocked` is not only a pre-submission condition. An agent can enter an approval or question UI during the delegated turn. Therefore the state graph MUST also permit

```text
prompt_submitted  -> blocked
activity_observed -> blocked
runtime_settled   -> blocked
```

The bridge MUST NOT translate these states into automatic approval or unrestricted `send_keys`.

## 4. Reply-marker evidence is regional, not global

The reply marker is present in the prompt frame itself. Therefore the predicate

$$
\mathrm{marker}\in\mathrm{terminal\_read}
$$

is insufficient to establish a turn-fenced reply.

A `turn_fenced` capture requires the marker to be found in a validated post-frame response region, or equivalent evidence that excludes the echoed prompt. If the screen redraw prevents that separation, confidence MUST be downgraded to `heuristic` unless a structured reply exists.

The preferred hierarchy remains

$$
\mathrm{structured}>\mathrm{turn\_fenced}>\mathrm{heuristic}.
$$

## 5. Updated exceptional state edges

The v0.1.1 implementation state graph is:

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

Exceptional edges include:

```text
resolving_target  -> target_unavailable
ready             -> blocked
ready             -> suppressed
ready             -> uncertain
prompt_submitted  -> blocked
prompt_submitted  -> uncertain
activity_observed -> blocked
activity_observed -> uncertain
runtime_settled   -> blocked
runtime_settled   -> capture_failed
runtime_settled   -> uncertain
*                 -> failed where the transition is semantically valid
```

This patch is the normative state behavior used by Runtime MVP v0.1.
