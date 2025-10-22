"""Tests for HTML generation components."""

import sys
from decimal import Decimal
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

from html_generation.portfolio_engine import PortfolioEngine
from html_generation.templates import (
    PROVIDER_NAMES,
    base_css,
    render_html_page,
    render_leaderboard,
)


def test_portfolio_engine_compute_cash_balance() -> None:
    """Test cash balance computation."""
    engine = PortfolioEngine()

    orders = [
        {"action": "BUY", "quantity": 10, "price": 100},
        {"action": "SELL", "quantity": 5, "price": 110},
    ]

    cash = engine.compute_cash_balance(Decimal("10000"), orders)

    # 10000 - (10 * 100) + (5 * 110) = 10000 - 1000 + 550 = 9550
    assert cash == Decimal("9550")


def test_portfolio_engine_compute_positions_market_value() -> None:
    """Test market value computation."""
    engine = PortfolioEngine()

    positions = [
        {"symbol": "AAPL", "quantity": 10},
        {"symbol": "GOOGL", "quantity": 5},
    ]

    prices = {
        "AAPL": Decimal("150"),
        "GOOGL": Decimal("2800"),
    }

    mv = engine.compute_positions_market_value(positions, prices)

    # (10 * 150) + (5 * 2800) = 1500 + 14000 = 15500
    assert mv == Decimal("15500")


def test_portfolio_engine_compute_realized_pl() -> None:
    """Test realized P/L computation with FIFO."""
    engine = PortfolioEngine()

    orders = [
        {"symbol": "AAPL", "action": "BUY", "quantity": 10, "price": 100},
        {"symbol": "AAPL", "action": "BUY", "quantity": 5, "price": 105},
        {"symbol": "AAPL", "action": "SELL", "quantity": 8, "price": 110},
    ]

    pl = engine.compute_realized_pl_from_orders(orders)

    # FIFO: Sell 8 shares
    # - First 10 shares bought at 100, sell 8 at 110: (110-100)*8 = 80
    assert pl == Decimal("80")


def test_portfolio_engine_build_trade_history() -> None:
    """Test trade history building."""
    engine = PortfolioEngine()

    orders = [
        {
            "symbol": "AAPL",
            "action": "BUY",
            "quantity": 10,
            "price": 100,
            "placed_at": "2025-10-01T10:00:00Z",
            "rationale": "Initial buy",
        },
        {
            "symbol": "AAPL",
            "action": "SELL",
            "quantity": 5,
            "price": 110,
            "placed_at": "2025-10-02T10:00:00Z",
            "rationale": "Take profit",
        },
    ]

    events, _inventory = engine.build_trade_history(Decimal("10000"), orders)

    assert len(events) == 2

    # First event: BUY
    assert events[0]["action"] == "BUY"
    assert events[0]["cash_balance"] == Decimal("9000")  # 10000 - 1000
    assert events[0]["position_after"] == Decimal("10")

    # Second event: SELL
    assert events[1]["action"] == "SELL"
    assert events[1]["cash_balance"] == Decimal("9550")  # 9000 + 550
    assert events[1]["position_after"] == Decimal("5")
    assert events[1]["realized_pl_delta"] == Decimal("50")  # (110-100)*5


def test_portfolio_engine_deduplicate_orders_keeps_latest_open_lot() -> None:
    """Ensure duplicate opening orders (long & short) collapse to latest lot."""
    engine = PortfolioEngine()

    orders = [
        {"symbol": "AAPL", "action": "BUY", "quantity": 10, "price": 100, "placed_at": "2025-10-01 10:00:00"},
        {"symbol": "AAPL", "action": "BUY", "quantity": 12, "price": 102, "placed_at": "2025-10-02 10:00:00"},
        {"symbol": "TSLA", "action": "SELL_SHORT", "quantity": 4, "price": 250, "placed_at": "2025-10-02 09:00:00"},
        {"symbol": "TSLA", "action": "SELL_SHORT", "quantity": 5, "price": 255, "placed_at": "2025-10-03 09:00:00"},
        {"symbol": "AAPL", "action": "SELL", "quantity": 5, "price": 105, "placed_at": "2025-10-04 10:00:00"},
    ]

    deduped, removed = engine.deduplicate_orders(orders)

    assert len(deduped) == 3
    assert deduped[0]["quantity"] == 12  # Latest BUY retained
    assert deduped[1]["quantity"] == 5   # Latest SELL_SHORT retained
    assert len(removed) == 2
    removed_quantities = sorted(item["quantity"] for item in removed)
    assert removed_quantities == [4, 10]


def test_portfolio_engine_summarize_inventory() -> None:
    """Summarize inventory lots into aggregated positions."""
    engine = PortfolioEngine()

    inventory = {
        "AAPL": [
            (Decimal("5"), Decimal("100"), "long", "2025-10-01 10:00:00"),
            (Decimal("3"), Decimal("110"), "long", "2025-10-02 10:00:00"),
        ],
        "TSLA": [
            (Decimal("4"), Decimal("250"), "short", "2025-10-03 09:00:00"),
        ],
    }

    positions = engine.summarize_inventory(inventory)

    assert len(positions) == 2
    longs = next(p for p in positions if p["side"] == "long")
    shorts = next(p for p in positions if p["side"] == "short")
    assert longs["symbol"] == "AAPL"
    assert longs["quantity"] == Decimal("8")
    # Weighted average price = (5*100 + 3*110)/8 = 103.75
    assert longs["avg_entry_price"] == Decimal("103.75")
    assert shorts["symbol"] == "TSLA"
    assert shorts["quantity"] == Decimal("4")
    assert shorts["avg_entry_price"] == Decimal("250")


def test_provider_names_mapping() -> None:
    """Test provider name constants."""
    assert PROVIDER_NAMES["openai"] == "OpenAI"
    assert PROVIDER_NAMES["gemini"] == "Gemini"
    assert PROVIDER_NAMES["anthropic"] == "Anthropic"


def test_base_css_contains_essential_styles() -> None:
    """Test that base CSS contains essential styles."""
    css = base_css()

    assert "font-family" in css
    assert "table" in css
    assert ".positive" in css
    assert ".negative" in css


def test_render_html_page() -> None:
    """Test HTML page rendering."""
    html = render_html_page("Test Title", "<p>Test content</p>")

    assert "<!DOCTYPE html>" in html
    assert "<title>Test Title</title>" in html
    assert "<p>Test content</p>" in html
    assert base_css() in html


def test_render_leaderboard() -> None:
    """Test leaderboard rendering."""
    strategies = [
        {
            "id": "strat-1",
            "name": "Strategy One",
            "payload": {"initial_capital_usd": 100000},
        },
        {
            "id": "strat-2",
            "name": "Strategy Two",
            "payload": {"initial_capital_usd": 100000},
        },
    ]

    portfolio_accounts = {
        "strat-1": [
            {
                "provider_id": "openai",
                "cash_balance": 60000,
                "equity_value": 50000,
            }
        ],
        "strat-2": [
            {
                "provider_id": "gemini",
                "cash_balance": 55000,
                "equity_value": 40000,
            }
        ],
    }

    # Add the third parameter: all_strategy_provider_pairs
    all_pairs = [
        ("strat-1", "openai"),
        ("strat-2", "gemini"),
    ]

    html = render_leaderboard(strategies, portfolio_accounts, all_pairs)

    assert "Strategy Leaderboard" in html
    assert "Strategy One" in html
    assert "Strategy Two" in html
    assert "+10.00%" in html
    assert "-5.00%" in html


def test_portfolio_engine_handles_none_prices() -> None:
    """Test that portfolio engine handles None prices gracefully."""
    engine = PortfolioEngine()

    orders = [
        {"action": "BUY", "quantity": 10, "price": None},  # None price
        {"action": "SELL", "quantity": 5, "price": 110},
    ]

    # Should not raise an error
    cash = engine.compute_cash_balance(Decimal("10000"), orders)
    assert cash == Decimal("10550")  # 10000 - 0 + 550


def test_portfolio_engine_compute_unrealized_pl() -> None:
    """Test unrealized P/L computation."""
    engine = PortfolioEngine()

    positions = [
        {"symbol": "AAPL", "quantity": 10, "avg_entry_price": 100},
        {"symbol": "GOOGL", "quantity": 5, "avg_entry_price": 2700},
    ]

    prices = {
        "AAPL": Decimal("110"),  # +10 per share
        "GOOGL": Decimal("2800"),  # +100 per share
    }

    result = engine.compute_unrealized_pl(positions, prices)

    # AAPL: (110-100)*10 = 100
    # GOOGL: (2800-2700)*5 = 500
    # Total: 600
    assert result["total"] == Decimal("600")
    assert result["by_symbol"]["AAPL"] == Decimal("100")
    assert result["by_symbol"]["GOOGL"] == Decimal("500")
