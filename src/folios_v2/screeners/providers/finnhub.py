"""Finnhub-backed screener implementation."""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from folios_v2.domain import ScreenerProviderId

from ..exceptions import ScreenerError
from ..interfaces import ScreenerProvider
from ..models import ScreenerResult


class FinnhubScreener(ScreenerProvider):
    """Adapter that fetches and filters symbols using the Finnhub API."""

    API_BASE = "https://finnhub.io/api/v1"
    DEFAULT_UNIVERSE_CAP = 2_000

    provider_id = ScreenerProviderId.FINNHUB

    def __init__(
        self,
        *,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
        max_concurrency: int = 8,
    ) -> None:
        resolved = token or os.getenv("FINNHUB_API_KEY")
        if not resolved:
            msg = "FINNHUB_API_KEY is not configured"
            raise ScreenerError(msg)
        self._token = resolved
        self._client = client
        self._timeout = timeout
        self._max_concurrency = max(1, max_concurrency)

    async def screen(
        self,
        *,
        filters: dict[str, Any],
        limit: int,
        universe_cap: int | None = None,
    ) -> ScreenerResult:
        limit = max(1, int(limit))
        universe_limit = max(1, int(universe_cap or self.DEFAULT_UNIVERSE_CAP))
        async with self._client_scope() as client:
            symbols = await self._list_symbols(client, filters)
            universe = symbols[:universe_limit]
            if not universe:
                return ScreenerResult.empty(provider=self.provider_id, filters=dict(filters))

            metrics = await self._gather_map(universe, self._fetch_metric, client)
            prelim = [
                symbol
                for symbol in universe
                if self._passes_fundamental_prefilter(metrics.get(symbol, {}), filters)
            ]
            quotes = await self._gather_map(prelim, self._fetch_quote, client)
            ranked: list[tuple[str, float]] = []
            for symbol in prelim:
                metric = metrics.get(symbol, {})
                quote = quotes.get(symbol, {})
                if self._passes_filters(metric, quote, filters):
                    ranked.append((symbol, float(metric.get("marketCap") or 0.0)))

        ranked.sort(key=lambda item: item[1], reverse=True)
        selected = tuple(symbol for symbol, _ in ranked[:limit])
        metadata = {
            "universe_size": len(symbols),
            "universe_sampled": len(universe),
            "prefilter_count": len(prelim),
            "returned_count": len(selected),
        }
        return ScreenerResult(
            provider=self.provider_id,
            symbols=selected,
            filters=dict(filters),
            metadata=metadata,
        )

    async def _list_symbols(
        self,
        client: httpx.AsyncClient,
        filters: dict[str, Any],
    ) -> list[str]:
        country = str(filters.get("country") or "US").upper()
        exchange_filter = str(filters.get("exchange") or "").upper()
        payload = await self._request(client, "/stock/symbol", {"exchange": country})
        if not isinstance(payload, list):
            return []
        tickers: list[str] = []
        for item in payload:
            symbol = str(item.get("symbol") or "").upper()
            if not symbol:
                continue
            if exchange_filter:
                exch = str(item.get("exchange") or item.get("mic") or "").upper()
                if exchange_filter not in exch and exchange_filter != exch:
                    continue
            tickers.append(symbol)
        return tickers

    async def _fetch_metric(
        self,
        client: httpx.AsyncClient,
        symbol: str,
    ) -> tuple[str, dict[str, Any]] | None:
        data = await self._request(client, "/stock/metric", {"symbol": symbol, "metric": "all"})
        metric = data.get("metric") if isinstance(data, dict) else None
        if isinstance(metric, dict):
            return symbol, metric
        return symbol, {}

    async def _fetch_quote(
        self,
        client: httpx.AsyncClient,
        symbol: str,
    ) -> tuple[str, dict[str, Any]] | None:
        quote = await self._request(client, "/quote", {"symbol": symbol})
        if isinstance(quote, dict):
            return symbol, quote
        return symbol, {}

    async def _gather_map(
        self,
        symbols: Iterable[str],
        fetcher: Callable[[httpx.AsyncClient, str], Awaitable[tuple[str, dict[str, Any]] | None]],
        client: httpx.AsyncClient,
    ) -> dict[str, dict[str, Any]]:
        semaphore = asyncio.Semaphore(self._max_concurrency)
        results: dict[str, dict[str, Any]] = {}

        async def _runner(sym: str) -> None:
            if not sym:
                return
            async with semaphore:
                try:
                    payload = await fetcher(client, sym)
                except ScreenerError:
                    raise
                except Exception:
                    return
                if isinstance(payload, tuple) and len(payload) == 2:
                    key, value = payload
                    if isinstance(key, str) and isinstance(value, dict):
                        results[key] = value

        tasks = [_runner(symbol) for symbol in symbols if symbol]
        if not tasks:
            return results
        await asyncio.gather(*tasks)
        return results

    def _passes_fundamental_prefilter(
        self,
        metric: dict[str, Any],
        filters: dict[str, Any],
    ) -> bool:
        mc_min = float(filters.get("market_cap_min") or 0.0)
        pe_max = float(filters.get("pe_max") or 9e12)
        roe_min = float(filters.get("roe_min") or 0.0)
        beta_max = float(filters.get("beta_max") or 9e12)
        dy_min = float(filters.get("dividend_yield_min") or 0.0)
        de_max = float(filters.get("debt_to_equity_max") or 9e12)

        market_cap = float(metric.get("marketCap") or 0.0)
        pe = float(metric.get("peBasicExclExtraTTM") or metric.get("trailingPE") or 9e12)
        roe = float(metric.get("roeTTM") or 0.0)
        beta = float(metric.get("beta") or 0.0)
        dy = float(metric.get("dividendYieldTTM") or 0.0)
        de = float(metric.get("debtToEquityTTM") or 9e12)

        return (
            market_cap >= mc_min
            and pe <= pe_max
            and roe >= roe_min
            and beta <= beta_max
            and dy >= dy_min
            and de <= de_max
        )

    def _passes_filters(
        self,
        metric: dict[str, Any],
        quote: dict[str, Any],
        filters: dict[str, Any],
    ) -> bool:
        if not self._passes_fundamental_prefilter(metric, filters):
            return False

        price_min = float(filters.get("price_min") or 0.0)
        price_max = float(filters.get("price_max") or 9e12)
        vol_min = float(filters.get("avg_vol_min") or 0.0)

        price = float(quote.get("c") or 0.0)
        volume = float(quote.get("v") or 0.0)

        return price_min <= price <= price_max and volume >= vol_min

    async def _request(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any],
    ) -> object:
        query = dict(params)
        query["token"] = self._token
        try:
            response = await client.get(
                f"{self.API_BASE}{path}",
                params=query,
            )
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            msg = f"Finnhub request failed with status {exc.response.status_code}"
            raise ScreenerError(msg) from exc
        except httpx.HTTPError as exc:
            msg = "Finnhub request failed"
            raise ScreenerError(msg) from exc

    @asynccontextmanager
    async def _client_scope(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            yield client


__all__ = ["FinnhubScreener"]
