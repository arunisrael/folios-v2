"""Service responsible for executing strategy screeners."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from folios_v2.domain import ScreenerProviderId, StrategyScreener

from .exceptions import ScreenerError
from .interfaces import ScreenerProvider
from .models import ScreenerResult


class ScreenerService:
    """Lookup registry and execution facade for screener providers."""

    def __init__(self) -> None:
        self._providers: dict[ScreenerProviderId, ScreenerProvider] = {}

    def register(self, provider: ScreenerProvider, *, override: bool = False) -> None:
        """Register a screener provider implementation."""

        existing = self._providers.get(provider.provider_id)
        if existing and not override:
            msg = f"Provider {provider.provider_id} is already registered"
            raise ScreenerError(msg)
        self._providers[provider.provider_id] = provider

    def require(self, provider_id: ScreenerProviderId) -> ScreenerProvider:
        try:
            return self._providers[provider_id]
        except KeyError as exc:
            msg = f"Screener provider {provider_id} is not registered"
            raise ScreenerError(msg) from exc

    def available_providers(self) -> tuple[ScreenerProviderId, ...]:
        return tuple(self._providers.keys())

    async def run(
        self,
        config: StrategyScreener,
        *,
        extra_filters: Mapping[str, Any] | None = None,
    ) -> ScreenerResult:
        """Execute the configured screener and normalize the result."""

        if not config.enabled:
            return ScreenerResult.empty(provider=config.provider, filters=config.filters)

        provider = self.require(config.provider)
        filters: dict[str, Any] = dict(config.filters)
        if extra_filters:
            filters.update(extra_filters)

        try:
            result = await provider.screen(
                filters=filters,
                limit=config.limit,
                universe_cap=config.universe_cap,
            )
        except ScreenerError:
            raise
        except Exception as exc:
            msg = f"Screener provider {config.provider} failed"
            raise ScreenerError(msg) from exc

        # Ensure we always return StrategyScreener filters for traceability.
        return ScreenerResult(
            provider=config.provider,
            symbols=tuple(result.symbols),
            filters=filters,
            fetched_at=result.fetched_at,
            metadata=dict(result.metadata),
        )


__all__ = ["ScreenerService"]
