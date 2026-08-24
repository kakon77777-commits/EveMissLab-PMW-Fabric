from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from typing import Callable

from .canonical import digest_ref
from .errors import WakeError
from .filesystem import read_allowlisted_payload
from .models import AckRecord, FailureRecord, WatchdogResult, WakeRequest
from .provider import NotificationAdapter, ProviderAdapter
from .store import WakeStore
from .temporal import TemporalProvider, UnavailableTemporalProvider


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


class WakeWatchdog:
    def __init__(
        self,
        store: WakeStore,
        provider: ProviderAdapter,
        notifier: NotificationAdapter,
        watchdog_id: str,
        *,
        temporal: TemporalProvider | None = None,
        clock: Callable[[], datetime] = _utc_now,
    ) -> None:
        self.store = store
        self.provider = provider
        self.notifier = notifier
        self.watchdog_id = watchdog_id
        self.temporal = temporal or UnavailableTemporalProvider()
        self.clock = clock

    def _result(self, wake_id: str, status: str, **details) -> WatchdogResult:
        return WatchdogResult(wake_id=wake_id, status=status, details=details)

    def _failure(self, request: WakeRequest, code: str, message: str, **details) -> WatchdogResult:
        record = FailureRecord(
            schema_version="eml-wake/failure-0.1",
            wake_id=request.wake_id,
            code=code,
            message=message,
            recorded_at=_iso(self.clock()),
            details=details,
        )
        self.store.record_failure(request.wake_id, record.to_dict())
        return self._result(request.wake_id, code, **details)

    def _policy_refusal(self, request: WakeRequest) -> tuple[str, str] | None:
        config = self.store.config
        if request.target_kind == "exact_instance":
            return "exact_instance_spawn_refused", "Version 1 never spawns for exact-instance targets"
        if request.target_kind not in config.allowed_target_kinds:
            return "target_kind_not_allowed", "target kind is not allowed by watchdog config"
        if not request.spawn_allowed:
            return "spawn_authority_missing", "spawn_allowed is false"
        if request.model not in config.allowed_models:
            return "model_not_allowed", "model is not allowed by watchdog config"
        allowed_tool_sets = {tuple(value) for value in config.allowed_tools_by_policy.values()}
        if tuple(request.allowed_tools) not in allowed_tool_sets:
            return "tools_policy_not_allowed", "allowed_tools do not match an allowed policy"
        if request.permission_mode not in config.permission_modes:
            return "permission_mode_not_allowed", "permission mode is not allowed"
        if request.max_budget_microusd > config.maximum_budget_microusd:
            return "budget_exceeds_policy", "request budget exceeds configured maximum"
        if request.timeout_ms > config.maximum_timeout_ms:
            return "timeout_exceeds_policy", "request timeout exceeds configured maximum"
        return None

    def _expired(self, request: WakeRequest) -> bool:
        expires = datetime.fromisoformat(request.expires_at[:-1] + "+00:00")
        return self.clock().astimezone(timezone.utc) >= expires

    @staticmethod
    def _prompt(request: WakeRequest, payload: str) -> str:
        return payload

    def process(self, wake_id: str) -> WatchdogResult:
        current = self.store.status(wake_id)
        if current["status"] == "acknowledged":
            return self._result(wake_id, "acknowledged", already_complete=True)
        if current["status"] == "failed":
            return self._result(wake_id, str(current["record"].get("code", "failed")), already_complete=True)
        if current["status"] == "claimed_incomplete":
            return self._result(wake_id, "claimed_incomplete")

        request = self.store.get_request(wake_id)
        refusal = self._policy_refusal(request)
        if refusal is not None:
            return self._failure(request, refusal[0], refusal[1])
        if self._expired(request):
            return self._failure(request, "request_expired", "wake request expired before claim")

        try:
            payload = read_allowlisted_payload(request, self.store.config)
        except WakeError as exc:
            return self._failure(request, exc.code, exc.message, **exc.details)
        try:
            payload_text = payload.data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return self._failure(request, "payload_invalid_utf8", "Version 1 payload must be UTF-8 text")

        try:
            self.store.claim(request.wake_id, self.watchdog_id)
        except WakeError as exc:
            if exc.code == "wake_already_claimed":
                return self._result(request.wake_id, "claimed_incomplete", concurrent_claim_lost=True)
            raise
        prompt = self._prompt(request, payload_text)
        try:
            provider_result = self.provider.invoke(request, prompt)
        except WakeError as exc:
            return self._failure(request, exc.code, exc.message, **exc.details)
        except Exception as exc:
            return self._failure(request, "provider_failed", str(exc))
        if provider_result.is_error:
            code = "provider_busy" if provider_result.api_error_status == 529 else "provider_failed"
            return self._failure(request, code, "provider returned an error result")

        recorded_at = _iso(self.clock())
        reply_digest = "sha256:" + hashlib.sha256(provider_result.result_text.encode("utf-8")).hexdigest()
        try:
            temporal = self.temporal.register(
                "EML wake ACK",
                {
                    "wake_id": request.wake_id,
                    "request_core_digest": request.core_digest,
                    "payload_sha256": payload.sha256,
                    "provider_session_id": provider_result.provider_session_id,
                    "reply_digest": reply_digest,
                },
            )
        except Exception:
            temporal = UnavailableTemporalProvider("ctcl_adapter_failed").register("", {})
        ack = AckRecord(
            schema_version="eml-wake/ack-0.1",
            wake_id=request.wake_id,
            request_time_ref=request.created_time_ref,
            request_digest=digest_ref(request.to_dict()),
            request_core_digest=request.core_digest,
            payload_sha256=payload.sha256,
            status="acknowledged",
            provider=provider_result.provider,
            model=provider_result.model,
            provider_session_id=provider_result.provider_session_id,
            watchdog_invocation_id=provider_result.watchdog_invocation_id,
            result_text=provider_result.result_text,
            provider_is_error=provider_result.is_error,
            provider_subtype=provider_result.subtype,
            provider_stop_reason=provider_result.stop_reason,
            permission_denials=provider_result.permission_denials,
            cost_microusd=provider_result.cost_microusd,
            duration_ms=provider_result.duration_ms,
            api_error_status=provider_result.api_error_status,
            temporal_evidence_status=temporal.status,
            temporal_instant_id=temporal.instant_id,
            temporal_receipt=temporal.receipt,
            temporal_error_code=temporal.error_code,
            weak_recorded_time=recorded_at,
            reply_digest=reply_digest,
            not_claimed=(
                "resident continuity",
                "identity of a historical interactive instance",
                "phenomenal subjectivity",
            ),
        )
        self.store.commit_ack(request.wake_id, ack.to_dict())
        try:
            notification = self.notifier.notify(ack)
            notification_record = notification.to_dict()
            notification_record.update(
                {
                    "schema_version": "eml-wake/notification-0.1",
                    "wake_id": request.wake_id,
                    "recorded_at": _iso(self.clock()),
                }
            )
            self.store.record_notification(request.wake_id, notification_record)
        except Exception:
            pass
        return self._result(request.wake_id, "acknowledged", ack_path=str(self.store.ack_path(request.wake_id)))

    def run_once(self) -> list[WatchdogResult]:
        return [self.process(wake_id) for wake_id in self.store.pending_wake_ids()]
