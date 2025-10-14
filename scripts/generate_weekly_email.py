"""Generate weekly email digest HTML.

Outputs to public/email/:
- week-{date}.html
- latest.html

Usage:
    python -m scripts.generate_weekly_email \
        --db folios_v2.db \
        --out public/email \
        --since 2025-10-01 \
        --until 2025-10-08
"""

from __future__ import annotations

import argparse
import asyncio
import html
from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine

from scripts.html_generation.data_loader import HTMLDataLoader
from scripts.html_generation.market_data import MarketDataService
from scripts.html_generation.templates import render_weekly_email


def _render_popular_holdings_html(
    popular_counts: Counter[str],
    prices: dict[str, Decimal]
) -> str:
    """Render popular holdings table.

    Args:
        popular_counts: Counter of symbols to holding count
        prices: Current prices by symbol

    Returns:
        HTML table of popular holdings
    """
    rows = []
    for symbol, count in popular_counts.most_common(20):
        price = prices.get(symbol, Decimal("0"))
        rows.append(f"""
        <tr style="border-bottom: 1px solid #e1e4e8;">
            <td style="padding: 12px;">{html.escape(symbol)}</td>
            <td style="padding: 12px;">{count}</td>
            <td style="padding: 12px;">${price:,.2f}</td>
        </tr>
        """)

    return f"""
    <table style="width: 100%; border-collapse: collapse;">
        <thead>
            <tr style="background-color: #f6f8fa; border-bottom: 1px solid #e1e4e8;">
                <th style="padding: 12px; text-align: left;">Symbol</th>
                <th style="padding: 12px; text-align: left;">Strategies</th>
                <th style="padding: 12px; text-align: left;">Current Price</th>
            </tr>
        </thead>
        <tbody>
            {"".join(rows) if rows else "<tr><td colspan='3' style='padding: 12px;'>No holdings</td></tr>"}
        </tbody>
    </table>
    """


def _render_weekly_activity_html(
    orders: list[dict],
    id_to_name: dict[str, str]
) -> str:
    """Render weekly activity summary.

    Args:
        orders: List of orders for the week
        id_to_name: Strategy ID to name mapping

    Returns:
        HTML summary of weekly activity
    """
    if not orders:
        return "<p>No activity this week</p>"

    # Group by strategy
    by_strategy: dict[str, list[dict]] = {}
    for order in orders:
        sid = order.get("strategy_id", "")
        if sid not in by_strategy:
            by_strategy[sid] = []
        by_strategy[sid].append(order)

    sections = []
    for sid, strategy_orders in by_strategy.items():
        strategy_name = id_to_name.get(sid, "Unknown")
        buy_count = sum(1 for o in strategy_orders if o.get("action") in ("BUY", "BUY_TO_COVER"))
        sell_count = sum(1 for o in strategy_orders if o.get("action") in ("SELL", "SELL_SHORT"))

        sections.append(f"""
        <div style="margin: 16px 0; padding: 16px; background-color: #f6f8fa; border-radius: 6px;">
            <h3 style="margin: 0 0 8px 0;">{html.escape(strategy_name)}</h3>
            <p style="margin: 0; color: #586069;">{buy_count} buys, {sell_count} sells</p>
        </div>
        """)

    return "".join(sections)


async def main() -> None:
    """Main entry point for weekly email generation."""
    parser = argparse.ArgumentParser(description="Generate weekly email digest")
    parser.add_argument("--db", default="folios_v2.db", help="Database file path")
    parser.add_argument("--out", default="public/email", help="Output directory")
    parser.add_argument("--since", default=None, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--until", default=None, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    # Date range (default: last 7 days)
    if args.until:
        until_date = datetime.fromisoformat(args.until)
    else:
        until_date = datetime.utcnow()

    if args.since:
        since_date = datetime.fromisoformat(args.since)
    else:
        since_date = until_date - timedelta(days=7)

    engine = create_engine(f"sqlite:///{args.db}")
    loader = HTMLDataLoader(engine)
    market_svc = MarketDataService(engine)

    print(f"Generating weekly digest for {since_date.date()} → {until_date.date()}")

    strategies = loader.load_strategies()
    id_to_name = {s["id"]: s["name"] for s in strategies}
    print(f"Found {len(strategies)} strategies")

    # Load weekly orders
    orders = loader.load_orders(since=since_date, until=until_date, status="filled")
    print(f"Found {len(orders)} orders in date range")

    # Build start/end snapshots for position delta
    start_snaps: dict[str, dict[str, float]] = {}
    end_snaps: dict[str, dict[str, float]] = {}
    all_symbols: set[str] = set()

    for strategy in strategies:
        sid = strategy["id"]
        start_snap = loader.get_position_snapshot(sid, as_of=since_date)
        end_snap = loader.get_position_snapshot(sid, as_of=until_date)
        start_snaps[sid] = start_snap
        end_snaps[sid] = end_snap
        all_symbols.update(start_snap.keys())
        all_symbols.update(end_snap.keys())

    # Fetch prices
    print(f"Fetching prices for {len(all_symbols)} symbols...")
    prices = await market_svc.get_current_prices(sorted(all_symbols))

    # Aggregate weekly activity
    total_buys = sum(1 for o in orders if o.get("action") in ("BUY", "BUY_TO_COVER"))
    total_sells = sum(1 for o in orders if o.get("action") in ("SELL", "SELL_SHORT"))

    opened_count = sum(
        len(set(end_snaps.get(s["id"], {}).keys()) - set(start_snaps.get(s["id"], {}).keys()))
        for s in strategies
    )
    closed_count = sum(
        len(set(start_snaps.get(s["id"], {}).keys()) - set(end_snaps.get(s["id"], {}).keys()))
        for s in strategies
    )

    # Popular holdings (from end snapshots)
    popular_counts: Counter[str] = Counter()
    for sid, positions in end_snaps.items():
        for sym, qty in positions.items():
            if qty > 0:
                popular_counts[sym] += 1

    # Build email sections
    hero_text = (
        f"Across {len(strategies)} strategies: {total_buys} buys, {total_sells} sells. "
        f"{opened_count} positions opened, {closed_count} closed."
    )

    sections: list[tuple[str, str]] = [
        ("Popular Holdings", _render_popular_holdings_html(popular_counts, prices)),
        ("Weekly Activity", _render_weekly_activity_html(orders, id_to_name)),
    ]

    html_out = render_weekly_email(
        title=f"Weekly Strategy Digest ({since_date.date()} → {until_date.date()})",
        hero_text=hero_text,
        sections=sections,
        generated_at=datetime.utcnow()
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Write dated file
    dated_file = out_dir / f"week-{until_date.date()}.html"
    dated_file.write_text(html_out, encoding="utf-8")
    print(f"  ✓ {dated_file}")

    # Write latest.html
    latest_file = out_dir / "latest.html"
    latest_file.write_text(html_out, encoding="utf-8")
    print(f"  ✓ {latest_file}")

    print("\n✅ Generated weekly email digest")
    print(f"   Output directory: {out_dir.absolute()}")


if __name__ == "__main__":
    asyncio.run(main())
