#!/usr/bin/env python3
"""Remove duplicate open orders and rebuild positions.

This utility mirrors the deduplication logic used by the HTML generator
(`PortfolioEngine.deduplicate_orders`) and applies the same pruning directly
to the SQLite database. For each strategy/provider pair we:

1. Load all filled orders.
2. Drop superseded open BUY / SELL_SHORT orders (keeping the most recent lot).
3. Reconstruct the open position snapshot from the remaining orders.
4. Replace the `positions` table entries with the recomputed snapshot.

After running this script, follow up with `scripts/recompute_portfolio_accounts.py`
to refresh cash/equity balances.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, text

from html_generation.data_loader import HTMLDataLoader
from html_generation.portfolio_engine import PortfolioEngine


def _build_in_clause(column: str, values: list[str]) -> tuple[str, dict[str, Any]]:
    """Construct an IN clause with positional parameters."""
    placeholders = []
    params: dict[str, Any] = {}
    for idx, value in enumerate(values):
        param_name = f"{column}_{idx}"
        placeholders.append(f":{param_name}")
        params[param_name] = value
    clause = f"{column} IN ({', '.join(placeholders)})"
    return clause, params


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Remove duplicate open lots from orders and rebuild positions."
    )
    parser.add_argument("--db", default="folios_v2.db", help="SQLite database path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show planned deletions/replacements without writing changes.",
    )
    args = parser.parse_args()

    engine = create_engine(f"sqlite:///{args.db}")
    loader = HTMLDataLoader(engine)
    portfolio_engine = PortfolioEngine()

    strategies = {s["id"]: s for s in loader.load_strategies()}

    with engine.begin() as conn:
        combos = conn.execute(
            text(
                "SELECT DISTINCT strategy_id, provider_id "
                "FROM orders WHERE status = 'filled'"
            )
        ).fetchall()

        total_removed_orders = 0
        total_positions_inserted = 0

        for combo in combos:
            strategy_id = combo.strategy_id
            provider_id = combo.provider_id
            orders = loader.load_orders(
                strategy_id=strategy_id,
                provider_id=provider_id,
                status="filled",
            )

            if not orders:
                continue

            deduped_orders, removed_orders = portfolio_engine.deduplicate_orders(orders)

            removed_count = 0
            if removed_orders:
                order_ids = [order["id"] for order in removed_orders if order.get("id")]
                clause, params = _build_in_clause("id", order_ids)
                if not args.dry_run:
                    conn.execute(text(f"DELETE FROM orders WHERE {clause}"), params)
                removed_count = len(order_ids)
                total_removed_orders += removed_count

            # Recompute inventory snapshot from the remaining orders
            strategy_payload = strategies.get(strategy_id, {}).get("payload", {}) or {}
            initial_capital = Decimal(
                str(strategy_payload.get("initial_capital_usd", 100000))
            )

            deduped_chrono = sorted(
                deduped_orders, key=lambda order: order.get("placed_at") or ""
            )
            _events, inventory = portfolio_engine.build_trade_history(
                initial_capital=initial_capital,
                orders=deduped_chrono,
            )
            summarized_positions = portfolio_engine.summarize_inventory(inventory)

            # Remove current open positions for this strategy/provider
            delete_params = {"strategy_id": strategy_id}
            if provider_id is None:
                delete_sql = (
                    "DELETE FROM positions "
                    "WHERE strategy_id = :strategy_id "
                    "AND provider_id IS NULL "
                    "AND status = 'open'"
                )
            else:
                delete_sql = (
                    "DELETE FROM positions "
                    "WHERE strategy_id = :strategy_id "
                    "AND provider_id = :provider_id "
                    "AND status = 'open'"
                )
                delete_params["provider_id"] = provider_id

            if not args.dry_run:
                conn.execute(text(delete_sql), delete_params)

            inserted_this_combo = 0
            if summarized_positions and not args.dry_run:
                now_iso = datetime.now(timezone.utc).isoformat()
                for pos in summarized_positions:
                    position_id = str(uuid4())
                    opened_at = pos.get("opened_at") or now_iso
                    payload = {
                        "id": position_id,
                        "strategy_id": strategy_id,
                        "provider_id": provider_id,
                        "symbol": pos["symbol"],
                        "side": pos.get("side", "long"),
                        "quantity": str(pos.get("quantity", 0)),
                        "average_price": str(pos.get("avg_entry_price", 0)),
                        "opened_at": opened_at,
                        "closed_at": None,
                        "metadata": {"recomputed_at": now_iso},
                    }
                    conn.execute(
                        text(
                            "INSERT INTO positions "
                            "(id, strategy_id, provider_id, symbol, status, opened_at, closed_at, payload) "
                            "VALUES (:id, :strategy_id, :provider_id, :symbol, 'open', :opened_at, NULL, :payload)"
                        ),
                        {
                            "id": position_id,
                            "strategy_id": strategy_id,
                            "provider_id": provider_id,
                            "symbol": pos["symbol"],
                            "opened_at": opened_at,
                            "payload": json.dumps(payload),
                        },
                    )
                    inserted_this_combo += 1

            total_positions_inserted += inserted_this_combo

            if args.dry_run and (removed_orders or summarized_positions):
                provider_label = provider_id or "default"
                print(
                    f"[DRY RUN] {strategy_id} / {provider_label}: "
                    f"would remove {len(removed_orders)} orders "
                    f"and reinsert {len(summarized_positions)} positions"
                )

        print("Cleanup summary:")
        print(f"  Orders removed: {total_removed_orders}")
        if args.dry_run:
            print("  Positions rebuilt: dry run (no changes applied)")
        else:
            print(f"  Positions inserted: {total_positions_inserted}")


if __name__ == "__main__":
    main()
