"""Value objects returned by screener providers."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import Field

from folios_v2.domain import DomainModel, ScreenerProviderId


def utc_now() -> datetime:
    return datetime.now(UTC)


class ScreenerResult(DomainModel):
    """Normalized output from a screener provider run."""

    provider: ScreenerProviderId
    symbols: tuple[str, ...] = Field(default_factory=tuple)
    filters: dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def empty(
        cls,
        *,
        provider: ScreenerProviderId,
        filters: dict[str, Any] | None = None,
    ) -> ScreenerResult:
        return cls(provider=provider, filters=filters or {})


__all__ = ["ScreenerResult"]
