"""Comprehensive tests for the Market Data Service."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from folios_v2.market_data import get_current_price, get_current_prices


# Fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures" / "yahoo_finance"


def load_fixture(filename: str) -> dict:
    """Load a JSON fixture file."""
    fixture_path = FIXTURES_DIR / filename
    with open(fixture_path) as f:
        return json.load(f)


class MockFastInfo:
    """Mock yfinance fast_info object."""

    def __init__(self, last_price: float | None):
        self.last_price = last_price


class MockTicker:
    """Mock yfinance Ticker object."""

    def __init__(
        self,
        fast_info_price: float | None = None,
        info_data: dict | None = None,
        history_df: pd.DataFrame | None = None,
        raise_fast_info_error: bool = False,
        raise_info_error: bool = False,
        raise_history_error: bool = False,
    ):
        self._fast_info_price = fast_info_price
        self._info_data = info_data or {}
        self._history_df = history_df if history_df is not None else pd.DataFrame()
        self._raise_fast_info_error = raise_fast_info_error
        self._raise_info_error = raise_info_error
        self._raise_history_error = raise_history_error

    @property
    def fast_info(self) -> MockFastInfo:
        if self._raise_fast_info_error:
            raise AttributeError("Fast info not available")
        return MockFastInfo(self._fast_info_price)

    @property
    def info(self) -> dict:
        if self._raise_info_error:
            raise AttributeError("Info not available")
        return self._info_data

    def history(self, period: str = "1d", interval: str = "1m") -> pd.DataFrame:
        if self._raise_history_error:
            raise AttributeError("History not available")
        return self._history_df


class TestGetCurrentPrice:
    """Tests for get_current_price function."""

    def test_successful_price_fetch_from_fast_info(self) -> None:
        """Test successful price fetching using fast_info."""
        fixture = load_fixture("aapl_success.json")
        expected_price = Decimal(str(fixture["fast_info"]["last_price"]))

        mock_ticker = MockTicker(fast_info_price=fixture["fast_info"]["last_price"])

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            price = asyncio.run(get_current_price("AAPL"))
            assert price == expected_price
            assert isinstance(price, Decimal)

    def test_successful_price_fetch_from_info_when_fast_info_fails(self) -> None:
        """Test price fetching falls back to info dict when fast_info fails."""
        fixture = load_fixture("msft_success.json")
        expected_price = Decimal(str(fixture["info"]["currentPrice"]))

        mock_ticker = MockTicker(
            raise_fast_info_error=True, info_data=fixture["info"]
        )

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            price = asyncio.run(get_current_price("MSFT"))
            assert price == expected_price
            assert isinstance(price, Decimal)

    def test_successful_price_fetch_from_regular_market_price(self) -> None:
        """Test price fetching uses regularMarketPrice when currentPrice is missing."""
        info_data = {
            "symbol": "GOOGL",
            "regularMarketPrice": 142.65,
            "currentPrice": None,
        }
        expected_price = Decimal("142.65")

        mock_ticker = MockTicker(raise_fast_info_error=True, info_data=info_data)

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            price = asyncio.run(get_current_price("GOOGL"))
            assert price == expected_price

    def test_successful_price_fetch_from_history_fallback(self) -> None:
        """Test price fetching falls back to history when fast_info and info fail."""
        fixture = load_fixture("history_fallback.json")
        expected_price = Decimal(str(fixture["history"]["last_close"]))

        # Create a DataFrame with Close prices
        hist_data = pd.DataFrame(
            {
                "Open": [100.50, 101.80, 103.30],
                "High": [102.30, 103.50, 104.00],
                "Low": [100.20, 101.60, 102.90],
                "Close": [101.75, 103.25, 103.88],
                "Volume": [5000000, 4800000, 5200000],
            }
        )

        mock_ticker = MockTicker(
            raise_fast_info_error=True, raise_info_error=True, history_df=hist_data
        )

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            price = asyncio.run(get_current_price("TEST"))
            assert price == expected_price

    def test_invalid_symbol_raises_value_error(self) -> None:
        """Test that invalid symbols raise ValueError."""
        mock_ticker = MockTicker(
            fast_info_price=None,
            info_data={"currentPrice": None, "regularMarketPrice": None},
            history_df=pd.DataFrame(),
        )

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(ValueError, match="Unable to fetch price for INVALID"):
                asyncio.run(get_current_price("INVALID"))

    def test_zero_price_raises_value_error(self) -> None:
        """Test that zero prices are treated as invalid."""
        fixture = load_fixture("zero_price.json")

        mock_ticker = MockTicker(
            fast_info_price=0, info_data=fixture["info"], history_df=pd.DataFrame()
        )

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(ValueError, match="Unable to fetch price"):
                asyncio.run(get_current_price("DELISTED"))

    def test_negative_price_raises_value_error(self) -> None:
        """Test that negative prices are treated as invalid."""
        mock_ticker = MockTicker(
            fast_info_price=-10.5,
            info_data={"currentPrice": -10.5},
            history_df=pd.DataFrame(),
        )

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(ValueError, match="Unable to fetch price"):
                asyncio.run(get_current_price("NEGATIVE"))

    def test_all_methods_fail_raises_value_error(self) -> None:
        """Test that ValueError is raised when all fetch methods fail."""
        mock_ticker = MockTicker(
            raise_fast_info_error=True,
            raise_info_error=True,
            raise_history_error=True,
        )

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(ValueError, match="Unable to fetch price"):
                asyncio.run(get_current_price("BROKEN"))

    def test_empty_history_dataframe_raises_value_error(self) -> None:
        """Test that empty history DataFrame is handled correctly."""
        mock_ticker = MockTicker(
            raise_fast_info_error=True,
            raise_info_error=True,
            history_df=pd.DataFrame(),
        )

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            with pytest.raises(ValueError, match="Unable to fetch price"):
                asyncio.run(get_current_price("EMPTY"))

    def test_api_connection_error_raises_value_error(self) -> None:
        """Test that API connection errors are properly handled."""

        def raise_connection_error(symbol: str):
            raise ConnectionError("Unable to connect to Yahoo Finance API")

        with patch(
            "folios_v2.market_data.yf.Ticker", side_effect=raise_connection_error
        ):
            with pytest.raises(ConnectionError):
                asyncio.run(get_current_price("AAPL"))


class TestGetCurrentPrices:
    """Tests for get_current_prices batch function."""

    def test_successful_batch_price_fetch(self) -> None:
        """Test successful batch price fetching for multiple symbols."""
        fixtures = {
            "AAPL": load_fixture("aapl_success.json"),
            "MSFT": load_fixture("msft_success.json"),
            "GOOGL": load_fixture("googl_success.json"),
        }

        def mock_ticker_factory(symbol: str) -> MockTicker:
            if symbol in fixtures:
                return MockTicker(
                    fast_info_price=fixtures[symbol]["fast_info"]["last_price"]
                )
            return MockTicker(fast_info_price=None)

        with patch("folios_v2.market_data.yf.Ticker", side_effect=mock_ticker_factory):
            prices = asyncio.run(get_current_prices(["AAPL", "MSFT", "GOOGL"]))

            assert len(prices) == 3
            assert prices["AAPL"] == Decimal(
                str(fixtures["AAPL"]["fast_info"]["last_price"])
            )
            assert prices["MSFT"] == Decimal(
                str(fixtures["MSFT"]["fast_info"]["last_price"])
            )
            assert prices["GOOGL"] == Decimal(
                str(fixtures["GOOGL"]["fast_info"]["last_price"])
            )

    def test_batch_with_some_invalid_symbols(self) -> None:
        """Test batch fetching with mix of valid and invalid symbols."""
        fixtures = {
            "AAPL": load_fixture("aapl_success.json"),
        }

        def mock_ticker_factory(symbol: str) -> MockTicker:
            if symbol == "AAPL":
                return MockTicker(
                    fast_info_price=fixtures["AAPL"]["fast_info"]["last_price"]
                )
            # Return invalid ticker for other symbols
            return MockTicker(
                fast_info_price=None,
                info_data={},
                history_df=pd.DataFrame(),
            )

        with patch("folios_v2.market_data.yf.Ticker", side_effect=mock_ticker_factory):
            prices = asyncio.run(get_current_prices(["AAPL", "INVALID1", "INVALID2"]))

            assert len(prices) == 3
            assert prices["AAPL"] == Decimal(
                str(fixtures["AAPL"]["fast_info"]["last_price"])
            )
            # Invalid symbols should return Decimal("0")
            assert prices["INVALID1"] == Decimal("0")
            assert prices["INVALID2"] == Decimal("0")

    def test_batch_with_all_invalid_symbols(self) -> None:
        """Test batch fetching when all symbols are invalid."""
        mock_ticker = MockTicker(
            fast_info_price=None, info_data={}, history_df=pd.DataFrame()
        )

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            prices = asyncio.run(get_current_prices(["INVALID1", "INVALID2", "INVALID3"]))

            assert len(prices) == 3
            assert all(price == Decimal("0") for price in prices.values())

    def test_empty_symbol_list(self) -> None:
        """Test batch fetching with empty symbol list."""
        prices = asyncio.run(get_current_prices([]))
        assert prices == {}

    def test_single_symbol_batch(self) -> None:
        """Test batch fetching with single symbol."""
        fixture = load_fixture("aapl_success.json")
        mock_ticker = MockTicker(fast_info_price=fixture["fast_info"]["last_price"])

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            prices = asyncio.run(get_current_prices(["AAPL"]))

            assert len(prices) == 1
            assert prices["AAPL"] == Decimal(
                str(fixture["fast_info"]["last_price"])
            )

    def test_batch_handles_exceptions_gracefully(self, capsys) -> None:
        """Test that batch processing continues even when some requests fail."""

        def mock_ticker_factory(symbol: str) -> MockTicker:
            if symbol == "ERROR":
                raise RuntimeError("Simulated API error")
            return MockTicker(fast_info_price=100.0)

        with patch("folios_v2.market_data.yf.Ticker", side_effect=mock_ticker_factory):
            prices = asyncio.run(get_current_prices(["AAPL", "ERROR", "MSFT"]))

            # Should have results for all symbols
            assert len(prices) == 3
            assert prices["AAPL"] == Decimal("100.0")
            assert prices["ERROR"] == Decimal("0")  # Failed fetch returns 0
            assert prices["MSFT"] == Decimal("100.0")

            # Verify warning was printed
            captured = capsys.readouterr()
            assert "Warning: Could not fetch price for ERROR" in captured.out


class TestCachingBehavior:
    """Tests for caching behavior (note: current implementation doesn't cache)."""

    def test_no_caching_multiple_calls(self) -> None:
        """Test that multiple calls for the same symbol make separate API requests.

        Note: The current implementation does not include caching.
        This test documents the current behavior and can be updated
        when caching is implemented.
        """
        mock_ticker = MockTicker(fast_info_price=175.43)

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker) as mock_yf:
            # Make three calls for the same symbol
            asyncio.run(get_current_price("AAPL"))
            asyncio.run(get_current_price("AAPL"))
            asyncio.run(get_current_price("AAPL"))

            # Without caching, yf.Ticker should be called 3 times
            assert mock_yf.call_count == 3


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_symbol_with_special_characters(self) -> None:
        """Test symbols with special characters (e.g., BRK.B)."""
        mock_ticker = MockTicker(fast_info_price=350.25)

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            price = asyncio.run(get_current_price("BRK.B"))
            assert price == Decimal("350.25")

    def test_very_small_price(self) -> None:
        """Test handling of very small prices (penny stocks)."""
        mock_ticker = MockTicker(fast_info_price=0.0001)

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            price = asyncio.run(get_current_price("PENNY"))
            assert price == Decimal("0.0001")

    def test_very_large_price(self) -> None:
        """Test handling of very large prices."""
        mock_ticker = MockTicker(fast_info_price=123456.78)

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            price = asyncio.run(get_current_price("EXPENSIVE"))
            assert price == Decimal("123456.78")

    def test_decimal_precision_maintained(self) -> None:
        """Test that decimal precision is maintained."""
        mock_ticker = MockTicker(fast_info_price=123.456789)

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            price = asyncio.run(get_current_price("PRECISE"))
            # Verify it's a Decimal with proper precision
            assert isinstance(price, Decimal)
            assert price == Decimal("123.456789")

    def test_concurrent_requests_same_symbol(self) -> None:
        """Test multiple concurrent requests for the same symbol."""
        mock_ticker = MockTicker(fast_info_price=175.43)

        async def run_concurrent():
            tasks = [get_current_price("AAPL") for _ in range(5)]
            return await asyncio.gather(*tasks)

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            results = asyncio.run(run_concurrent())
            # All should return the same price
            assert all(price == Decimal("175.43") for price in results)

    def test_history_with_nan_values(self) -> None:
        """Test handling of NaN values in history DataFrame."""
        import numpy as np

        hist_data = pd.DataFrame(
            {
                "Open": [100.0, np.nan, 103.0],
                "High": [102.0, np.nan, 104.0],
                "Low": [100.0, np.nan, 103.0],
                "Close": [101.0, np.nan, 103.5],
                "Volume": [5000000, 0, 5200000],
            }
        )

        mock_ticker = MockTicker(
            raise_fast_info_error=True, raise_info_error=True, history_df=hist_data
        )

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker):
            # Should get the last non-NaN close price
            price = asyncio.run(get_current_price("TEST"))
            assert price == Decimal("103.5")

    def test_mixed_case_symbols(self) -> None:
        """Test that symbols are handled regardless of case."""
        mock_ticker = MockTicker(fast_info_price=100.0)

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker) as mock_yf:
            asyncio.run(get_current_price("aapl"))
            mock_yf.assert_called_with("aapl")

            asyncio.run(get_current_price("AAPL"))
            mock_yf.assert_called_with("AAPL")

    def test_whitespace_in_symbol(self) -> None:
        """Test handling of symbols with whitespace."""
        mock_ticker = MockTicker(fast_info_price=100.0)

        with patch("folios_v2.market_data.yf.Ticker", return_value=mock_ticker) as mock_yf:
            asyncio.run(get_current_price(" AAPL "))
            # Verify the symbol is passed as-is (no trimming in current implementation)
            mock_yf.assert_called_with(" AAPL ")
