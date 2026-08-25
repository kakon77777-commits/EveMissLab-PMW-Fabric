from __future__ import annotations


class IntegrationContractError(RuntimeError):
    """Typed failure at an integration contract boundary."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
