"""Protocols for screener providers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from folios_v2.domain import ScreenerProviderId

from .models import ScreenerResult


class ScreenerProvider(Protocol):
    """Contract implemented by screener provider adapters."""

    provider_id: ScreenerProviderId

    async def screen(
        self,
        *,
        filters: Mapping[str, Any],
        limit: int,
        universe_cap: int | None = None,
    ) -> ScreenerResult:
        """Return tickers that satisfy the supplied filters."""


__all__ = ["ScreenerProvider"]
