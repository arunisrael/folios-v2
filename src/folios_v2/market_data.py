"""Market data service for fetching stock prices."""

from __future__ import annotations

import asyncio
from decimal import Decimal

import yfinance as yf


async def get_current_price(symbol: str) -> Decimal:
    """Get current price for a symbol using Yahoo Finance.

    Args:
        symbol: Stock symbol (e.g., "AAPL", "MSFT")

    Returns:
        Current price as Decimal

    Raises:
        ValueError: If price cannot be fetched
    """
    # Run in thread pool to avoid blocking
    loop = asyncio.get_event_loop()
    ticker = await loop.run_in_executor(None, yf.Ticker, symbol)

    # Try to get current price from fast_info
    try:
        price = await loop.run_in_executor(None, lambda: ticker.fast_info.last_price)
        if price and price > 0:
            return Decimal(str(price))
    except (AttributeError, KeyError, TypeError):
        pass

    # Fallback to info dict
    try:
        info = await loop.run_in_executor(None, lambda: ticker.info)
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        if price and price > 0:
            return Decimal(str(price))
    except (AttributeError, KeyError, TypeError):
        pass

    # Last resort: get most recent history
    try:
        hist = await loop.run_in_executor(
            None,
            lambda: ticker.history(period="1d", interval="1m")
        )
        if not hist.empty:
            price = hist["Close"].iloc[-1]
            if price and price > 0:
                return Decimal(str(price))
    except (AttributeError, KeyError, IndexError, TypeError):
        pass

    raise ValueError(f"Unable to fetch price for {symbol}")


async def get_current_prices(symbols: list[str]) -> dict[str, Decimal]:
    """Get current prices for multiple symbols.

    Args:
        symbols: List of stock symbols

    Returns:
        Dictionary mapping symbol to current price
    """
    tasks = [get_current_price(symbol) for symbol in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    prices = {}
    for symbol, result in zip(symbols, results, strict=False):
        if isinstance(result, Decimal):
            prices[symbol] = result
        elif isinstance(result, Exception):
            # Log error but continue
            print(f"Warning: Could not fetch price for {symbol}: {result}")
            prices[symbol] = Decimal("0")

    return prices


__all__ = ["get_current_price", "get_current_prices"]
