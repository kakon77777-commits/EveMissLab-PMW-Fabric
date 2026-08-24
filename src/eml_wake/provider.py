from __future__ import annotations

from collections import deque
from typing import Protocol
import uuid

from .errors import WakeError
from .models import AckRecord, NotificationResult, ProviderResult, WakeRequest


class ProviderAdapter(Protocol):
    def invoke(self, request: WakeRequest, prompt: str) -> ProviderResult: ...


class NotificationAdapter(Protocol):
    def notify(self, ack: AckRecord) -> NotificationResult: ...


class FakeProviderAdapter:
    def __init__(self) -> None:
        self._outcomes: deque[ProviderResult | Exception] = deque()
        self.invocation_count = 0
        self.prompts: list[str] = []
        self.requests: list[WakeRequest] = []

    def queue(self, outcome: ProviderResult | Exception) -> None:
        self._outcomes.append(outcome)

    def invoke(self, request: WakeRequest, prompt: str) -> ProviderResult:
        self.invocation_count += 1
        self.requests.append(request)
        self.prompts.append(prompt)
        if not self._outcomes:
            raise WakeError("fake_provider_empty", "fake provider has no queued outcome")
        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class NullNotifier:
    def notify(self, ack: AckRecord) -> NotificationResult:
        return NotificationResult(
            notification_id=f"notification:{uuid.uuid4()}",
            attempted=False,
            accepted=False,
        )


class FakeNotifier:
    def __init__(self) -> None:
        self._outcomes: deque[NotificationResult | Exception] = deque()
        self.notification_count = 0

    def queue(
        self,
        *,
        accepted: bool,
        error_code: str | None = None,
        route_kind: str = "ephemeral",
        ephemeral_route_ref: str = "ai-test",
    ) -> None:
        self._outcomes.append(
            NotificationResult(
                notification_id=f"notification:{uuid.uuid4()}",
                attempted=True,
                accepted=accepted,
                route_kind=route_kind,
                ephemeral_route_ref=ephemeral_route_ref,
                error_code=error_code,
            )
        )

    def notify(self, ack: AckRecord) -> NotificationResult:
        self.notification_count += 1
        if not self._outcomes:
            return NotificationResult(
                notification_id=f"notification:{uuid.uuid4()}",
                attempted=False,
                accepted=False,
            )
        outcome = self._outcomes.popleft()
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
