from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import pytest

from folios_v2.domain import ScreenerProviderId, StrategyScreener
from folios_v2.screeners import ScreenerError, ScreenerResult, ScreenerService


class FakeProvider:
    provider_id = ScreenerProviderId.FINNHUB

    async def screen(
        self,
        *,
        filters: Mapping[str, Any],
        limit: int,
        universe_cap: int | None = None,
    ) -> ScreenerResult:
        symbols = ("AAPL", "MSFT")
        metadata = {"limit": limit, "universe_cap": universe_cap}
        return ScreenerResult(
            provider=self.provider_id,
            symbols=symbols,
            filters=dict(filters),
            metadata=metadata,
        )


def test_screener_service_runs_provider() -> None:
    service = ScreenerService()
    service.register(FakeProvider())

    config = StrategyScreener(
        provider=ScreenerProviderId.FINNHUB,
        filters={"market_cap_min": 1_000_000_000},
        limit=5,
    )

    result = asyncio.run(service.run(config))
    assert result.symbols == ("AAPL", "MSFT")
    assert result.filters["market_cap_min"] == 1_000_000_000
    assert result.metadata["limit"] == 5


def test_screener_service_returns_empty_when_disabled() -> None:
    service = ScreenerService()
    service.register(FakeProvider())

    config = StrategyScreener(
        provider=ScreenerProviderId.FINNHUB,
        filters={},
        limit=5,
        enabled=False,
    )

    result = asyncio.run(service.run(config))
    assert result.symbols == ()


def test_screener_service_requires_registered_provider() -> None:
    service = ScreenerService()
    config = StrategyScreener(
        provider=ScreenerProviderId.FINNHUB,
        filters={},
        limit=5,
    )
    with pytest.raises(ScreenerError):
        asyncio.run(service.run(config))
