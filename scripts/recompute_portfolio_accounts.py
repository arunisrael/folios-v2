#!/usr/bin/env python3
"""Recompute portfolio account cash/equity balances from order history.

This script is intended to correct out-of-sync `portfolio_accounts` entries
where the stored cash balance no longer matches the executed trades. It
re-derives cash from the full order history and re-values open positions using
current market prices, then updates the JSON payload for each account.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

import sys

sys.path.insert(0, str(Path(__file__).parent))

from sqlalchemy import create_engine, text

from html_generation.data_loader import HTMLDataLoader
from html_generation.market_data import MarketDataService
from html_generation.portfolio_engine import PortfolioEngine


def _to_decimal(value: Any) -> Decimal:
    """Coerce a JSON value to Decimal."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="Recalculate portfolio_accounts cash/equity balances."
    )
    parser.add_argument("--db", default="folios_v2.db", help="SQLite database path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned updates without modifying the database.",
    )
    args = parser.parse_args()

    engine = create_engine(f"sqlite:///{args.db}")
    loader = HTMLDataLoader(engine)
    portfolio_engine = PortfolioEngine()
    market = MarketDataService(engine)

    strategies = {s["id"]: s for s in loader.load_strategies()}

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, strategy_id, provider_id, payload "
                "FROM portfolio_accounts ORDER BY strategy_id, provider_id"
            )
        ).fetchall()

    if not rows:
        print("No portfolio accounts found.")
        return

    positions_by_account: dict[str, list[dict[str, Any]]] = {}
    all_symbols: set[str] = set()

    for row in rows:
        positions = loader.load_positions(
            strategy_id=row.strategy_id,
            provider_id=row.provider_id,
            status="open",
        )
        positions_by_account[row.id] = positions
        for pos in positions:
            symbol = pos.get("symbol")
            if symbol:
                all_symbols.add(symbol)

    price_map: dict[str, Decimal] = {}
    if all_symbols:
        print(f"Fetching prices for {len(all_symbols)} symbols...")
        price_map = await market.get_current_prices(sorted(all_symbols))

    updates: list[tuple[str, str]] = []
    delta_summaries: list[str] = []
    now_iso = datetime.now(timezone.utc).isoformat()

    for row in rows:
        payload = row.payload
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        elif payload is None:
            payload = {}

        strategy = strategies.get(row.strategy_id)
        if strategy is None:
            print(f"Skipping account {row.id}: unknown strategy {row.strategy_id}")
            continue

        strat_payload = strategy.get("payload", {}) or {}
        initial_capital = Decimal(str(strat_payload.get("initial_capital_usd", 100000)))

        orders = loader.load_orders(
            strategy_id=row.strategy_id,
            provider_id=row.provider_id,
            status="filled",
        )
        recalculated_cash = portfolio_engine.compute_cash_balance(
            initial_capital=initial_capital,
            orders=orders,
        )

        positions = positions_by_account.get(row.id, [])
        recalculated_equity = Decimal("0")
        for pos in positions:
            symbol = pos.get("symbol")
            quantity = Decimal(str(pos.get("quantity", 0)))
            price = price_map.get(symbol, Decimal("0"))
            side = (pos.get("side") or "long").lower()
            market_value = quantity * price
            if side == "short":
                market_value = -market_value
            recalculated_equity += market_value

        old_cash = _to_decimal(payload.get("cash_balance", 0))
        old_equity = _to_decimal(payload.get("equity_value", 0))

        payload["cash_balance"] = str(recalculated_cash)
        payload["equity_value"] = str(recalculated_equity)
        payload["updated_at"] = now_iso

        payload_json = json.dumps(payload)
        updates.append((payload_json, row.id))

        delta_summaries.append(
            f"Strategy {row.strategy_id} / provider {row.provider_id or 'default'}: "
            f"cash {old_cash:,.2f} → {recalculated_cash:,.2f} "
            f"(Δ {(recalculated_cash - old_cash):,.2f}), "
            f"equity {old_equity:,.2f} → {recalculated_equity:,.2f}"
        )

    if args.dry_run:
        print("Dry run — no changes written. Planned updates:")
        for summary in delta_summaries:
            print(f"  - {summary}")
        return

    with engine.begin() as conn:
        for payload_json, account_id in updates:
            conn.execute(
                text("UPDATE portfolio_accounts SET payload = :payload WHERE id = :id"),
                {"payload": payload_json, "id": account_id},
            )

    print(f"Updated {len(updates)} portfolio accounts.")
    for summary in delta_summaries:
        print(f"  - {summary}")


if __name__ == "__main__":
    asyncio.run(main())
