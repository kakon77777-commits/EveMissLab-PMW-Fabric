from __future__ import annotations

from eml_wake.temporal import (
    CtclHttpTemporalProvider,
    TemporalProvider,
    TemporalReceipt,
    UnavailableTemporalProvider,
)


def temporal_provider(
    provider: TemporalProvider | None, endpoint: str
) -> TemporalProvider:
    return provider or CtclHttpTemporalProvider(endpoint=endpoint)


__all__ = [
    "CtclHttpTemporalProvider",
    "TemporalProvider",
    "TemporalReceipt",
    "UnavailableTemporalProvider",
    "temporal_provider",
]
