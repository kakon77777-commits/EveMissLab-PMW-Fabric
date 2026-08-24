from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from .capture import capture_reply
from .errors import HerdrTransportError, StaleBindingError
from .framing import build_prompt_frame
from .herdr import HerdrAdapter
from .ids import new_id
from .journal import SQLiteJournal
from .models import (
    AgentBinding,
    AgentInfo,
    CaptureConfidence,
    DeliveryResult,
    DeliveryState,
    now_iso,
)
from .sinks import BoardSink, NullBoardSink, NullProvenanceSink, ProvenanceSink


SETTLED = {"idle", "done", "blocked"}


class BridgeEngine:
    def __init__(
        self,
        *,
        journal: SQLiteJournal,
        herdr: HerdrAdapter,
        board_sink: BoardSink | None = None,
        provenance_sink: ProvenanceSink | None = None,
        prompt_effect_timeout_ms: int = 5_000,
        poll_interval_ms: int = 100,
        read_lines: int = 240,
        allow_heuristic_capture: bool = False,
        require_target_lock: bool = True,
    ):
        self.journal = journal
        self.herdr = herdr
        self.board_sink = board_sink or NullBoardSink()
        self.provenance_sink = provenance_sink or NullProvenanceSink()
        self.prompt_effect_timeout_ms = prompt_effect_timeout_ms
        self.poll_interval_ms = poll_interval_ms
        self.read_lines = read_lines
        self.allow_heuristic_capture = allow_heuristic_capture
        # Fail closed: a proactive send with no issued lock is refused, not delivered.
        self.require_target_lock = require_target_lock
        if self.journal.get_meta("runtime_epoch_id") is None:
            self.journal.set_meta("runtime_epoch_id", new_id("hep"))

    @property
    def runtime_epoch_id(self) -> str:
        value = self.journal.get_meta("runtime_epoch_id")
        assert value is not None
        return value

    def rotate_runtime_epoch(self) -> str:
        value = new_id("hep")
        self.journal.set_meta("runtime_epoch_id", value)
        self.journal.record_event("runtime_epoch.rotated", {"runtime_epoch_id": value})
        return value

    def bind_agent(
        self,
        semantic_agent_id: str,
        agent_target: str,
        *,
        display_name: str | None = None,
        role: str | None = None,
        herdr_session: str = "default",
    ) -> AgentBinding:
        live = self.herdr.get_agent(agent_target)
        previous = self.journal.get_agent(semantic_agent_id)
        launch_epoch = 1
        if previous is not None:
            launch_epoch = int(previous["runtime_binding"].get("launch_epoch", 0)) + 1
        confidence = "native_session" if live.agent_session else "runtime_identity"
        binding = AgentBinding(
            semantic_agent_id=semantic_agent_id,
            display_name=display_name or semantic_agent_id.rsplit("/", 1)[-1],
            role=role,
            binding_id=new_id("bind"),
            runtime_epoch_id=self.runtime_epoch_id,
            herdr_session=herdr_session,
            agent_target=agent_target,
            agent_kind=live.agent or "unknown",
            workspace_id=live.workspace_id,
            tab_id=live.tab_id,
            pane_id=live.pane_id,
            terminal_id=live.terminal_id,
            native_session_ref=live.agent_session,
            launch_epoch=launch_epoch,
            bound_at=now_iso(),
            status=live.agent_status,
            state_change_seq=live.state_change_seq,
            revision=live.revision,
            binding_confidence=confidence,
        )
        self.journal.upsert_agent(binding)
        self.journal.record_event(
            "agent.bound", binding.to_dict(), semantic_agent_id=semantic_agent_id
        )
        self.provenance_sink.stamp("agent.bound", binding.to_dict())
        return binding

    @staticmethod
    def _native_session_matches(binding: dict[str, Any], live: AgentInfo) -> bool:
        left = binding.get("native_session_ref")
        right = live.agent_session
        if not left or not right:
            return False
        return (
            left.get("agent") == right.get("agent")
            and left.get("kind") == right.get("kind")
            and left.get("value") == right.get("value")
        )

    def _refresh_binding(self, semantic_agent_id: str, record: dict[str, Any], live: AgentInfo) -> dict[str, Any]:
        binding = dict(record["runtime_binding"])
        if live.terminal_id != binding["terminal_id"] and not self._native_session_matches(binding, live):
            raise StaleBindingError(
                f"semantic identity {semantic_agent_id} no longer matches Herdr target {binding['agent_target']}"
            )
        binding.update(
            {
                "runtime_epoch_id": self.runtime_epoch_id,
                "workspace_id": live.workspace_id,
                "tab_id": live.tab_id,
                "pane_id": live.pane_id,
                "terminal_id": live.terminal_id,
                "agent_kind": live.agent or binding.get("agent_kind", "unknown"),
                "native_session_ref": live.agent_session,
                "status": live.agent_status,
                "state_change_seq": live.state_change_seq,
                "revision": live.revision,
            }
        )
        refreshed = AgentBinding(
            semantic_agent_id=semantic_agent_id,
            display_name=record["display_name"],
            role=record.get("role"),
            binding_id=binding["binding_id"],
            runtime_epoch_id=binding["runtime_epoch_id"],
            herdr_session=binding["herdr_session"],
            agent_target=binding["agent_target"],
            agent_kind=binding["agent_kind"],
            workspace_id=binding["workspace_id"],
            tab_id=binding["tab_id"],
            pane_id=binding["pane_id"],
            terminal_id=binding["terminal_id"],
            native_session_ref=binding.get("native_session_ref"),
            launch_epoch=int(binding["launch_epoch"]),
            bound_at=binding["bound_at"],
            status=binding["status"],
            state_change_seq=int(binding["state_change_seq"]),
            revision=int(binding["revision"]),
            binding_confidence=binding.get("binding_confidence", "runtime_identity"),
        )
        self.journal.upsert_agent(refreshed)
        return refreshed.to_dict()

    def reconcile_agent(self, semantic_agent_id: str) -> dict[str, Any]:
        record = self.journal.get_agent(semantic_agent_id)
        if record is None:
            raise KeyError(f"semantic agent not bound: {semantic_agent_id}")
        target = record["runtime_binding"]["agent_target"]
        live = self.herdr.get_agent(target)
        return self._refresh_binding(semantic_agent_id, record, live)

    def reconcile_all(self) -> list[dict[str, Any]]:
        results = []
        for record in self.journal.list_agents():
            semantic_id = record["semantic_agent_id"]
            try:
                binding = self.reconcile_agent(semantic_id)
                results.append({"semantic_agent_id": semantic_id, "status": "ok", "binding": binding})
            except Exception as exc:  # reconciliation report must continue across agents
                results.append({"semantic_agent_id": semantic_id, "status": "error", "error": str(exc)})
        return results

    def _transition(
        self,
        message_id: str,
        recipient_id: str,
        state: DeliveryState,
        *,
        details: dict[str, Any] | None = None,
        reply_text: str | None = None,
        confidence: CaptureConfidence | None = None,
    ) -> dict[str, Any]:
        record = self.journal.transition_delivery(
            message_id,
            recipient_id,
            state,
            details=details,
            reply_text=reply_text,
            capture_confidence=None if confidence is None else confidence.value,
        )
        event_payload = {
            "message_id": message_id,
            "recipient_id": recipient_id,
            "state": state.value,
            "details": details or {},
        }
        self.journal.record_event(
            "delivery.state", event_payload, semantic_agent_id=recipient_id, message_id=message_id
        )
        self.provenance_sink.stamp("delivery.state", event_payload)
        return record

    @staticmethod
    def _result_from_record(record: dict[str, Any]) -> DeliveryResult:
        confidence = record.get("capture_confidence") or CaptureConfidence.NONE.value
        return DeliveryResult(
            message_id=record["message_id"],
            recipient_id=record["recipient_id"],
            state=DeliveryState(record["state"]),
            reply_text=record.get("reply_text"),
            capture_confidence=CaptureConfidence(confidence),
            details=record.get("details") or {},
        )

    def _complete_structured_reply(
        self,
        message: dict,
        recipient_id: str,
        structured: dict[str, Any],
        *,
        runtime_settled: bool,
    ) -> DeliveryResult:
        captured = self._transition(
            message["message_id"],
            recipient_id,
            DeliveryState.REPLY_CAPTURED,
            details={
                "capture_evidence": {
                    "source": "structured_reply",
                    "runtime_settled": runtime_settled,
                }
            },
            reply_text=str(structured["text"]),
            confidence=CaptureConfidence.STRUCTURED,
        )
        if bool(message["delivery"].get("require_semantic_ack", True)):
            captured = self._transition(
                message["message_id"],
                recipient_id,
                DeliveryState.ACKNOWLEDGED,
                details={"semantic_ack": True},
            )
        self.board_sink.record_message(message, captured)
        return self._result_from_record(captured)

    def _loop_reason(self, message: dict, recipient_id: str) -> str | None:
        routing = message["routing"]
        if int(routing["hop_count"]) >= int(routing["max_hops"]):
            return "max_hops"
        if int(routing["auto_reply_depth"]) >= int(routing["max_auto_reply_depth"]):
            return "max_auto_reply_depth"
        if self.journal.route_seen(
            message["sender"]["semantic_agent_id"],
            recipient_id,
            message["thread_id"],
            routing["payload_hash"],
        ):
            return "duplicate_payload_route"
        return None

    def _wait_preexisting_work(self, target: str, status: str, timeout_ms: int) -> AgentInfo:
        if status != "working":
            return self.herdr.get_agent(target)
        return self.herdr.wait_agent(target, until=("idle", "done", "blocked"), timeout_ms=timeout_ms)

    def _observe_prompt_effect(self, target: str, before: AgentInfo, prompted: AgentInfo) -> AgentInfo | None:
        if prompted.state_change_seq > before.state_change_seq or prompted.agent_status != before.agent_status:
            return prompted
        deadline = time.monotonic() + self.prompt_effect_timeout_ms / 1000.0
        while time.monotonic() < deadline:
            current = self.herdr.get_agent(target)
            if current.state_change_seq > before.state_change_seq or current.agent_status != before.agent_status:
                return current
            time.sleep(max(self.poll_interval_ms, 1) / 1000.0)
        return None

    def _preflight_target_authority(
        self, message: dict, message_id: str, recipient_id: str
    ) -> DeliveryResult | None:
        """Recipient authority gate. Runs before every side effect, board sinks included.

        Returns a terminal DeliveryResult when the send is refused (Herdr prompt count
        stays 0), or None when delivery may proceed. The sending agent supplies only a
        lock id; the recipient is derived from the lock, never from the sender.
        """
        authority = dict(message.get("target_authority") or {})
        mode = str(authority.get("mode", "unlocked"))
        evidence: dict[str, Any] = {
            "mode": mode,
            "target_lock_id": authority.get("target_lock_id"),
            "user_requested_visible_title": authority.get("user_requested_visible_title"),
            "user_requested_semantic_id": authority.get("user_requested_semantic_id"),
            "user_requested_native_thread_id": authority.get("user_requested_native_thread_id"),
            "resolved_semantic_id": None,
            "resolved_native_thread_id": None,
            "actual_recipient_id": recipient_id,
            "allow_proxy": bool(authority.get("allow_proxy", False)),
        }

        def refuse(state: DeliveryState, reason: str) -> DeliveryResult:
            details = {
                "reason": reason,
                "side_effect": "no_herdr_prompt",
                "target_authority": dict(evidence),
            }
            record = self._transition(message_id, recipient_id, state, details=details)
            self.journal.record_event(
                "target_authority.refused",
                {"message_id": message_id, "state": state.value, **details},
                semantic_agent_id=recipient_id,
                message_id=message_id,
            )
            self.provenance_sink.stamp("target_authority.refused", details)
            return self._result_from_record(record)

        def allow(reason: str) -> None:
            details = {"target_authority": dict(evidence), "authority_basis": reason}
            self._transition(message_id, recipient_id, DeliveryState.JOURNALED, details=details)
            self.journal.record_event(
                "target_authority.passed",
                {"message_id": message_id, **details},
                semantic_agent_id=recipient_id,
                message_id=message_id,
            )

        # A reply's recipient comes from the parent message, not from a free choice,
        # so it carries its authority with it and needs no new lock.
        if mode == "parent_derived":
            evidence["resolved_semantic_id"] = recipient_id
            allow("parent_derived")
            return None

        lock_id = authority.get("target_lock_id")
        if not lock_id:
            if self.require_target_lock:
                return refuse(DeliveryState.TARGET_AUTHORITY_MISMATCH, "target_lock_required")
            allow("target_lock_not_required")
            return None

        lock = self.journal.get_target_lock(str(lock_id))
        if lock is None:
            return refuse(DeliveryState.TARGET_AUTHORITY_MISMATCH, "target_lock_not_found")
        if lock.is_revoked:
            return refuse(DeliveryState.TARGET_AUTHORITY_MISMATCH, "target_lock_revoked")

        # The lock, not the message, is the authority on what was requested.
        evidence["user_requested_visible_title"] = lock.requested_visible_title
        evidence["user_requested_semantic_id"] = lock.requested_semantic_agent_id
        evidence["user_requested_native_thread_id"] = lock.requested_native_thread_id
        evidence["allow_proxy"] = bool(lock.allow_proxy)

        if recipient_id != lock.requested_semantic_agent_id:
            return refuse(
                DeliveryState.TARGET_AUTHORITY_MISMATCH, "actual_recipient_not_equal_to_lock"
            )

        record = self.journal.get_agent(lock.requested_semantic_agent_id)
        if record is None:
            return refuse(
                DeliveryState.EXACT_NATIVE_TARGET_NOT_BOUND, "semantic_agent_not_bound"
            )

        binding = record["runtime_binding"]
        resolved_semantic = str(record["semantic_agent_id"])
        resolved_native = (binding.get("native_session_ref") or {}).get("value")
        evidence["resolved_semantic_id"] = resolved_semantic
        evidence["resolved_native_thread_id"] = resolved_native

        if resolved_semantic != lock.requested_semantic_agent_id:
            return refuse(
                DeliveryState.TARGET_AUTHORITY_MISMATCH, "resolved_semantic_not_equal_to_lock"
            )

        wanted_native = lock.requested_native_thread_id
        if wanted_native:
            if resolved_native is None:
                if not lock.allow_proxy:
                    return refuse(
                        DeliveryState.EXACT_NATIVE_TARGET_NOT_BOUND, "native_thread_ref_absent"
                    )
                evidence["proxy_used"] = True
            elif str(resolved_native) != str(wanted_native):
                if not lock.allow_proxy:
                    return refuse(
                        DeliveryState.EXACT_NATIVE_TARGET_NOT_BOUND, "native_thread_ref_mismatch"
                    )
                evidence["proxy_used"] = True

        allow("target_lock")
        return None

    def deliver(self, message: dict) -> DeliveryResult:
        recipient_id = message["recipients"][0]["semantic_agent_id"]
        message_id = self.journal.journal_message(message)
        self.journal.ensure_delivery(message_id, recipient_id)
        existing = self.journal.get_delivery(message_id, recipient_id)
        assert existing is not None
        if existing["state"] != DeliveryState.JOURNALED.value:
            # Never implicitly replay a side effect. Explicit recovery/reconcile is a later surface.
            return self._result_from_record(existing)

        refused = self._preflight_target_authority(message, message_id, recipient_id)
        if refused is not None:
            return refused

        projection = message["delivery"]["projection"]
        if projection in {"board_only", "board_and_prompt"}:
            board_ref = self.board_sink.record_message(message, existing)
            if board_ref:
                self.provenance_sink.stamp("board.recorded", {"message_id": message_id, "board_ref": board_ref})
        if projection == "board_only":
            self._transition(message_id, recipient_id, DeliveryState.RESOLVING_TARGET, details={"projection": projection})
            self._transition(message_id, recipient_id, DeliveryState.READY)
            record = self._transition(
                message_id,
                recipient_id,
                DeliveryState.SUPPRESSED,
                details={"reason": "board_only_projection", "side_effect": "no_herdr_prompt"},
            )
            return self._result_from_record(record)

        self._transition(message_id, recipient_id, DeliveryState.RESOLVING_TARGET)
        record = self.journal.get_agent(recipient_id)
        if record is None:
            final = self._transition(
                message_id,
                recipient_id,
                DeliveryState.TARGET_UNAVAILABLE,
                details={"reason": "semantic_agent_not_bound"},
            )
            return self._result_from_record(final)

        target = record["runtime_binding"]["agent_target"]
        try:
            live = self.herdr.get_agent(target)
            binding = self._refresh_binding(recipient_id, record, live)
        except (HerdrTransportError, StaleBindingError) as exc:
            final = self._transition(
                message_id,
                recipient_id,
                DeliveryState.TARGET_UNAVAILABLE,
                details={"reason": type(exc).__name__, "error": str(exc)},
            )
            return self._result_from_record(final)

        timeout_ms = int(message["delivery"]["timeout_ms"])
        if message["delivery"].get("strict_turn", True):
            if live.agent_status == "working":
                try:
                    live = self._wait_preexisting_work(target, live.agent_status, timeout_ms)
                except HerdrTransportError as exc:
                    final = self._transition(
                        message_id,
                        recipient_id,
                        DeliveryState.TARGET_UNAVAILABLE,
                        details={"reason": "preexisting_work_did_not_settle", "error": str(exc), "code": exc.code},
                    )
                    return self._result_from_record(final)
            if live.agent_status == "blocked":
                self._transition(message_id, recipient_id, DeliveryState.READY, details={"binding": binding})
                final = self._transition(
                    message_id,
                    recipient_id,
                    DeliveryState.BLOCKED,
                    details={"reason": "target_requires_interactive_input"},
                )
                return self._result_from_record(final)
            if live.agent_status == "unknown":
                final = self._transition(
                    message_id,
                    recipient_id,
                    DeliveryState.TARGET_UNAVAILABLE,
                    details={"reason": "target_status_unknown_strict_turn"},
                )
                return self._result_from_record(final)

        self._transition(message_id, recipient_id, DeliveryState.READY, details={"binding": binding})
        loop_reason = self._loop_reason(message, recipient_id)
        if loop_reason:
            final = self._transition(
                message_id,
                recipient_id,
                DeliveryState.SUPPRESSED,
                details={"reason": loop_reason},
            )
            return self._result_from_record(final)

        try:
            before_text = self.herdr.read_agent(target, lines=self.read_lines)
        except HerdrTransportError:
            before_text = ""

        # Absolute: the recipient's cwd is its own pane's, not the controller's, so a
        # relative --db in the hint would resolve against the wrong directory.
        frame = build_prompt_frame(message, recipient_id, journal_db=str(self.journal.path.resolve()))
        pre_prompt = live
        try:
            prompted = self.herdr.prompt_agent(target, frame)
        except HerdrTransportError as exc:
            if exc.code == "agent_blocked":
                final = self._transition(
                    message_id,
                    recipient_id,
                    DeliveryState.BLOCKED,
                    details={"reason": "agent_blocked_during_submit", "error": str(exc)},
                )
            elif exc.ambiguous:
                final = self._transition(
                    message_id,
                    recipient_id,
                    DeliveryState.UNCERTAIN,
                    details={"reason": "submission_ambiguous", "error": str(exc), "code": exc.code},
                )
            else:
                final = self._transition(
                    message_id,
                    recipient_id,
                    DeliveryState.FAILED,
                    details={"reason": "prompt_rejected", "error": str(exc), "code": exc.code},
                )
            return self._result_from_record(final)

        self._transition(
            message_id,
            recipient_id,
            DeliveryState.PROMPT_SUBMITTED,
            details={"agent": prompted.to_dict()},
        )
        self.journal.record_route(
            message["sender"]["semantic_agent_id"],
            recipient_id,
            message["thread_id"],
            message["routing"]["payload_hash"],
            message_id,
        )

        try:
            observed = self._observe_prompt_effect(target, pre_prompt, prompted)
        except HerdrTransportError as exc:
            final = self._transition(
                message_id,
                recipient_id,
                DeliveryState.UNCERTAIN,
                details={"reason": "effect_observation_transport_error", "error": str(exc), "code": exc.code},
            )
            return self._result_from_record(final)
        if observed is None:
            final = self._transition(
                message_id,
                recipient_id,
                DeliveryState.UNCERTAIN,
                details={"reason": "prompt_effect_not_observed", "effect_timeout_ms": self.prompt_effect_timeout_ms},
            )
            return self._result_from_record(final)

        if observed.agent_status == "blocked":
            self._transition(message_id, recipient_id, DeliveryState.ACTIVITY_OBSERVED, details={"agent": observed.to_dict()})
            final = self._transition(
                message_id,
                recipient_id,
                DeliveryState.BLOCKED,
                details={"reason": "agent_blocked_after_prompt"},
            )
            return self._result_from_record(final)

        self._transition(
            message_id,
            recipient_id,
            DeliveryState.ACTIVITY_OBSERVED,
            details={"agent": observed.to_dict()},
        )

        structured = self.journal.get_structured_reply(message_id, recipient_id)
        if structured is not None:
            return self._complete_structured_reply(
                message,
                recipient_id,
                structured,
                runtime_settled=observed.agent_status in SETTLED,
            )

        settled = observed
        if settled.agent_status not in SETTLED:
            try:
                settled = self.herdr.wait_agent(
                    target,
                    until=tuple(message["delivery"]["wait_until"]),
                    timeout_ms=timeout_ms,
                )
            except HerdrTransportError as exc:
                structured = self.journal.get_structured_reply(message_id, recipient_id)
                if structured is not None:
                    return self._complete_structured_reply(
                        message,
                        recipient_id,
                        structured,
                        runtime_settled=False,
                    )
                final = self._transition(
                    message_id,
                    recipient_id,
                    DeliveryState.UNCERTAIN if exc.ambiguous or exc.code == "timeout" else DeliveryState.FAILED,
                    details={"reason": "settled_wait_failed", "error": str(exc), "code": exc.code},
                )
                return self._result_from_record(final)

        if settled.agent_status == "blocked":
            final = self._transition(
                message_id,
                recipient_id,
                DeliveryState.BLOCKED,
                details={"reason": "agent_blocked_during_turn", "agent": settled.to_dict()},
            )
            return self._result_from_record(final)

        self._transition(
            message_id,
            recipient_id,
            DeliveryState.RUNTIME_SETTLED,
            details={"agent": settled.to_dict()},
        )

        structured = self.journal.get_structured_reply(message_id, recipient_id)
        structured_text = None if structured is None else str(structured["text"])
        try:
            after_text = self.herdr.read_agent(target, lines=self.read_lines)
        except HerdrTransportError as exc:
            if structured_text is None:
                final = self._transition(
                    message_id,
                    recipient_id,
                    DeliveryState.CAPTURE_FAILED,
                    details={"reason": "terminal_read_failed", "error": str(exc), "code": exc.code},
                )
                return self._result_from_record(final)
            after_text = ""

        capture = capture_reply(
            before_text,
            after_text,
            message["payload"]["reply_marker"],
            structured_text=structured_text,
        )
        require_ack = bool(message["delivery"].get("require_semantic_ack", True))
        acceptable = capture.confidence in {CaptureConfidence.STRUCTURED, CaptureConfidence.TURN_FENCED}
        if self.allow_heuristic_capture and capture.confidence == CaptureConfidence.HEURISTIC:
            acceptable = True

        if capture.text is None or (require_ack and not acceptable):
            final = self._transition(
                message_id,
                recipient_id,
                DeliveryState.CAPTURE_FAILED,
                details={"reason": "semantic_ack_not_captured", "capture_evidence": capture.evidence},
                reply_text=capture.text,
                confidence=capture.confidence,
            )
            return self._result_from_record(final)

        captured = self._transition(
            message_id,
            recipient_id,
            DeliveryState.REPLY_CAPTURED,
            details={"capture_evidence": capture.evidence},
            reply_text=capture.text,
            confidence=capture.confidence,
        )
        if require_ack:
            captured = self._transition(
                message_id,
                recipient_id,
                DeliveryState.ACKNOWLEDGED,
                details={"semantic_ack": True},
            )
        self.board_sink.record_message(message, captured)
        return self._result_from_record(captured)
