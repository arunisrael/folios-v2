"""Generate static HTML pages for strategies and portfolios.

Outputs to public/:
- index.html: Leaderboard
- strategy-{id}.html: Per-strategy details
- feed.html: Activity feed

Usage:
    python -m scripts.generate_public_html --db folios_v2.db --out public/
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from html_generation.data_loader import HTMLDataLoader
from html_generation.market_data import MarketDataService
from html_generation.portfolio_engine import PortfolioEngine
from html_generation.templates import (
    render_activity_feed,
    render_leaderboard,
    render_strategy_detail,
)


async def main() -> None:
    """Main entry point for HTML generation."""
    parser = argparse.ArgumentParser(description="Generate public HTML")
    parser.add_argument("--db", default="folios_v2.db", help="Database file path")
    parser.add_argument("--out", default="public", help="Output directory")
    args = parser.parse_args()

    # Setup
    engine = create_engine(f"sqlite:///{args.db}")
    loader = HTMLDataLoader(engine)
    market_svc = MarketDataService(engine)
    portfolio_engine = PortfolioEngine()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("Loading strategies...")
    strategies = loader.load_strategies()
    print(f"Found {len(strategies)} strategies")

    # Collect all symbols for batch price fetch
    all_symbols: set[str] = set()
    for strategy in strategies:
        sid = strategy["id"]
        positions = loader.load_positions(sid, status="open")
        for pos in positions:
            all_symbols.add(pos["symbol"])

    # Batch fetch prices
    print(f"Fetching prices for {len(all_symbols)} symbols...")
    prices = await market_svc.get_current_prices(sorted(all_symbols))
    print(f"Fetched {len([p for p in prices.values() if p > 0])} valid prices")

    # Build portfolio data for each strategy
    portfolio_accounts_by_strategy: dict[str, list[dict]] = {}
    positions_by_strategy: dict[str, dict[str | None, list[dict]]] = {}
    trade_history_by_strategy: dict[str, dict[str | None, list[dict]]] = {}

    print("Processing strategies...")
    for strategy in strategies:
        sid = strategy["id"]
        payload = strategy.get("payload", {})

        # Load portfolio accounts (provider-scoped)
        accounts = loader.load_portfolio_accounts(sid)
        portfolio_accounts_by_strategy[sid] = accounts

        # Get unique providers (from accounts + positions)
        providers: set[str | None] = {acc["provider_id"] for acc in accounts}
        positions = loader.load_positions(sid, status="open")
        providers.update(pos.get("provider_id") for pos in positions)

        if not providers:
            providers.add(None)  # legacy unscoped

        # Per-provider breakdown
        positions_by_provider: dict[str | None, list[dict]] = {}
        trade_history_by_provider: dict[str | None, list[dict]] = {}

        for provider_id in providers:
            pos = loader.load_positions(sid, provider_id=provider_id, status="open")
            positions_by_provider[provider_id] = pos

            orders = loader.load_orders(sid, provider_id=provider_id, status="filled")
            initial_capital = Decimal(str(payload.get("initial_capital_usd", 100000)))
            events, inventory = portfolio_engine.build_trade_history(
                initial_capital=initial_capital,
                orders=orders
            )
            trade_history_by_provider[provider_id] = events

        positions_by_strategy[sid] = positions_by_provider
        trade_history_by_strategy[sid] = trade_history_by_provider

    # Load all strategy+provider pairs from requests
    print("Loading strategy+provider pairs from requests...")
    all_pairs = loader.load_all_strategy_provider_pairs()
    print(f"Found {len(all_pairs)} strategy+provider pairs with requests")

    # Render leaderboard
    print("Rendering leaderboard...")
    index_html = render_leaderboard(
        strategies,
        portfolio_accounts_by_strategy,
        all_pairs,
        positions_by_strategy,
        prices
    )
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")
    print(f"  ✓ {out_dir / 'index.html'}")

    # Render per-strategy pages
    print("Rendering strategy detail pages...")
    for strategy in strategies:
        sid = strategy["id"]
        detail_html = render_strategy_detail(
            strategy,
            portfolio_accounts_by_strategy[sid],
            positions_by_strategy[sid],
            trade_history_by_strategy[sid],
            prices,
        )
        strategy_file = out_dir / f"strategy-{sid}.html"
        strategy_file.write_text(detail_html, encoding="utf-8")
        print(f"  ✓ {strategy_file}")

    # Render activity feed
    print("Rendering activity feed...")
    recent_orders = loader.load_recent_orders(limit=2000)
    strategy_map = {s["id"]: s["name"] for s in strategies}
    feed_html = render_activity_feed(recent_orders, strategy_map)
    (out_dir / "feed.html").write_text(feed_html, encoding="utf-8")
    print(f"  ✓ {out_dir / 'feed.html'}")

    print(f"\n✅ Generated {len(strategies)} strategy pages + index.html + feed.html")
    print(f"   Output directory: {out_dir.absolute()}")


if __name__ == "__main__":
    asyncio.run(main())
