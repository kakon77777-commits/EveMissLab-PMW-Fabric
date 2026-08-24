from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import re
from typing import Any, Protocol
from urllib.error import URLError
from urllib.request import Request, urlopen


_CTCL_RE = re.compile(
    r"^ctcl:instant:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class TemporalReceipt:
    status: str
    instant_id: str | None
    receipt: dict[str, Any] | None
    error_code: str | None


class TemporalProvider(Protocol):
    def register(self, label: str, meta: dict[str, Any]) -> TemporalReceipt: ...


class UnavailableTemporalProvider:
    def __init__(self, reason: str = "not_configured") -> None:
        self.reason = reason

    def register(self, label: str, meta: dict[str, Any]) -> TemporalReceipt:
        return TemporalReceipt("unavailable", None, None, self.reason)


class FakeTemporalProvider:
    def __init__(self) -> None:
        self._receipts: deque[TemporalReceipt | Exception] = deque()
        self.registration_count = 0
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def queue(self, receipt: TemporalReceipt | Exception) -> None:
        self._receipts.append(receipt)

    def register(self, label: str, meta: dict[str, Any]) -> TemporalReceipt:
        self.registration_count += 1
        self.calls.append((label, dict(meta)))
        if not self._receipts:
            return TemporalReceipt("unavailable", None, None, "fake_temporal_empty")
        receipt = self._receipts.popleft()
        if isinstance(receipt, Exception):
            raise receipt
        return receipt


class CtclHttpTemporalProvider:
    def __init__(
        self,
        *,
        endpoint: str = "https://commoninstant.org/v1/instants",
        opener=urlopen,
        timeout_s: float = 10.0,
    ) -> None:
        self.endpoint = endpoint
        self.opener = opener
        self.timeout_s = timeout_s

    @staticmethod
    def _unavailable(code: str) -> TemporalReceipt:
        return TemporalReceipt("unavailable", None, None, code)

    def register(self, label: str, meta: dict[str, Any]) -> TemporalReceipt:
        body = json.dumps(
            {"label": label, "meta": meta},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "EML-Wake/0.1 (+https://commoninstant.org)",
            },
            method="POST",
        )
        try:
            with self.opener(request, timeout=self.timeout_s) as response:
                raw = response.read()
        except (URLError, OSError, TimeoutError):
            return self._unavailable("ctcl_unavailable")
        try:
            envelope = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._unavailable("ctcl_response_invalid")
        if not isinstance(envelope, dict) or envelope.get("ok") is not True:
            return self._unavailable("ctcl_registration_failed")
        receipt = envelope.get("data")
        if not isinstance(receipt, dict):
            return self._unavailable("ctcl_response_invalid")
        instant_id = receipt.get("id")
        if not isinstance(instant_id, str) or not _CTCL_RE.fullmatch(instant_id):
            return self._unavailable("ctcl_response_invalid")
        if not isinstance(receipt.get("retrieve"), str) or not isinstance(receipt.get("share"), str):
            return self._unavailable("ctcl_response_invalid")
        return TemporalReceipt("registered_anchor", instant_id, receipt, None)
