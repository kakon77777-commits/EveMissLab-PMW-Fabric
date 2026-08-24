from __future__ import annotations


class BridgeError(RuntimeError):
    """Base bridge error."""


class HerdrTransportError(BridgeError):
    def __init__(self, message: str, *, code: str | None = None, ambiguous: bool = False, payload: dict | None = None):
        super().__init__(message)
        self.code = code
        self.ambiguous = ambiguous
        self.payload = payload or {}


class StaleBindingError(BridgeError):
    pass


class DeliverySuppressed(BridgeError):
    pass
