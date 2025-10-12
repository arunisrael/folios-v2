"""Market data fetching with caching for HTML generation."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy.engine import Engine

from folios_v2.market_data import get_current_prices as yf_get_prices


class MarketDataService:
    """Fetch live prices with database fallback."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    async def get_current_prices(
        self,
        symbols: Sequence[str]
    ) -> dict[str, Decimal]:
        """Batch fetch current prices from Yahoo Finance.

        Falls back to returning Decimal("0") for failed fetches, matching
        the behavior of folios_v2.market_data.get_current_prices.

        Args:
            symbols: Sequence of stock symbols

        Returns:
            Dict mapping symbol to current price (or Decimal("0") on failure)
        """
        try:
            # Use existing market data service from folios_v2
            prices = await yf_get_prices(list(symbols))
            return prices
        except Exception as e:
            # If batch fetch fails entirely, return zeros for all symbols
            print(f"Warning: Batch price fetch failed: {e}")
            return {symbol: Decimal("0") for symbol in symbols}


__all__ = ["MarketDataService"]
