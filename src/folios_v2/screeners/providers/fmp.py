"""Financial Modeling Prep screener implementation."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from typing import Any

import httpx

from folios_v2.domain import ScreenerProviderId

from ..exceptions import ScreenerError
from ..interfaces import ScreenerProvider
from ..models import ScreenerResult


class FMPScreener(ScreenerProvider):
    """Adapter targeting FMP's stock screener endpoints."""

    API_BASE = "https://financialmodelingprep.com"

    provider_id = ScreenerProviderId.FMP

    def __init__(
        self,
        *,
        token: str | None = None,
        client: httpx.AsyncClient | None = None,
        timeout: float = 30.0,
    ) -> None:
        resolved = token or os.getenv("FMP_API_KEY")
        if not resolved:
            msg = "FMP_API_KEY is not configured"
            raise ScreenerError(msg)
        self._token = resolved
        self._client = client
        self._timeout = timeout

    async def screen(
        self,
        *,
        filters: dict[str, Any],
        limit: int,
        universe_cap: int | None = None,
    ) -> ScreenerResult:
        params = self._map_filters(filters)
        params["limit"] = max(1, int(limit))

        async with self._client_scope() as client:
            payload = await self._request(client, "/api/v3/stock-screener", params, suppress=True)
            endpoint = "/api/v3/stock-screener"
            if not self._is_valid_payload(payload):
                fallback = await self._request(
                    client,
                    "/api/v4/stock-screener",
                    params,
                    suppress=True,
                )
                if self._is_valid_payload(fallback):
                    payload = fallback
                    endpoint = "/api/v4/stock-screener"

        symbols = self._extract_symbols(payload)
        metadata = {
            "endpoint": endpoint,
            "returned_count": len(symbols),
        }
        return ScreenerResult(
            provider=self.provider_id,
            symbols=tuple(symbols),
            filters=dict(filters),
            metadata=metadata,
        )

    def _map_filters(self, filters: dict[str, Any]) -> dict[str, Any]:
        params: dict[str, Any] = {}
        if filters.get("market_cap_min") is not None:
            params["marketCapMoreThan"] = int(float(filters["market_cap_min"]))
        if filters.get("market_cap_max") is not None:
            params["marketCapLowerThan"] = int(float(filters["market_cap_max"]))
        if filters.get("price_min") is not None:
            params["priceMoreThan"] = float(filters["price_min"])
        if filters.get("price_max") is not None:
            params["priceLowerThan"] = float(filters["price_max"])
        if filters.get("avg_vol_min") is not None:
            params["volumeMoreThan"] = int(float(filters["avg_vol_min"]))
        if filters.get("avg_vol_max") is not None:
            params["volumeLowerThan"] = int(float(filters["avg_vol_max"]))
        if filters.get("pe_max") is not None:
            params["peLowerThan"] = float(filters["pe_max"])
        if filters.get("pe_min") is not None:
            params["peMoreThan"] = float(filters["pe_min"])
        if filters.get("exchange") is not None:
            params["exchange"] = str(filters["exchange"])
        if filters.get("sector") is not None:
            params["sector"] = str(filters["sector"])
        if filters.get("industry") is not None:
            params["industry"] = str(filters["industry"])
        return params

    def _extract_symbols(self, payload: object) -> list[str]:
        symbols: list[str] = []
        if not isinstance(payload, Iterable):
            return symbols
        for item in payload:
            if not isinstance(item, dict):
                continue
            symbol = str(item.get("symbol") or "").upper()
            if symbol and symbol not in symbols:
                symbols.append(symbol)
        return symbols

    def _is_valid_payload(self, payload: object) -> bool:
        return isinstance(payload, list) and bool(payload)

    async def _request(
        self,
        client: httpx.AsyncClient,
        path: str,
        params: dict[str, Any],
        *,
        suppress: bool = False,
    ) -> Any:
        query = dict(params)
        query["apikey"] = self._token
        url = f"{self.API_BASE}{path}"
        try:
            response = await client.get(url, params=query)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if suppress:
                return []
            msg = f"FMP request failed with status {exc.response.status_code}"
            raise ScreenerError(msg) from exc
        except httpx.HTTPError as exc:  # noqa: PERF203
            if suppress:
                return []
            msg = "FMP request failed"
            raise ScreenerError(msg) from exc

    @asynccontextmanager
    async def _client_scope(self) -> AsyncIterator[httpx.AsyncClient]:
        if self._client is not None:
            yield self._client
            return
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            yield client


__all__ = ["FMPScreener"]
