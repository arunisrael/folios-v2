#!/usr/bin/env python3
"""Apply inline recommendations to strategy portfolios."""

import asyncio
import json
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import typer

from folios_v2.cli.deps import get_container
from folios_v2.domain import Order, PortfolioAccount, Position
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.trading import OrderAction, OrderStatus, PositionSide
from folios_v2.domain.types import OrderId, PositionId, StrategyId
from folios_v2.utils import utc_now
from folios_v2.utils.order_idempotency import add_order_if_new, build_order_idempotency_key

# Optional import for live prices
try:
    from folios_v2.market_data import get_current_price
except ImportError:
    get_current_price = None

app = typer.Typer(help="Apply inline recommendations to portfolios")


async def _initialize_portfolio_account(
    strategy_id: StrategyId,
    provider_id: ProviderId,
    initial_balance: Decimal,
) -> PortfolioAccount:
    """Initialize or fetch portfolio account."""
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        account = await uow.portfolio_repository.get(strategy_id, provider_id)
        if account is None:
            account = PortfolioAccount(
                strategy_id=strategy_id,
                provider_id=provider_id,
                cash_balance=initial_balance,
                equity_value=Decimal("0"),
                updated_at=utc_now(),
            )
            await uow.portfolio_repository.upsert(account)
            await uow.commit()
            print(f"  Created portfolio account with ${initial_balance:,.2f} initial balance")
        else:
            print(
                f"  Using existing portfolio: "
                f"cash=${account.cash_balance:,.2f}, equity=${account.equity_value:,.2f}"
            )
    return account


async def _execute_buy_order(
    strategy_id: StrategyId,
    provider_id: ProviderId,
    symbol: str,
    shares: int,
    current_price: Decimal,
    rationale: str = "",
) -> tuple[Order, Position]:
    """Execute a BUY order and create/update position."""
    quantity = Decimal(str(shares))

    # Build metadata with rationale
    key = build_order_idempotency_key(
        strategy_id,
        provider_id,
        symbol,
        OrderAction.BUY,
        quantity,
        current_price,
    )
    metadata = {"idempotency_key": key}
    if rationale:
        metadata["rationale"] = rationale

    # Create order
    order = Order(
        id=OrderId(uuid4()),
        strategy_id=strategy_id,
        provider_id=provider_id,
        symbol=symbol,
        action=OrderAction.BUY,
        quantity=quantity,
        limit_price=current_price,
        status=OrderStatus.FILLED,
        placed_at=utc_now(),
        filled_at=utc_now(),
        metadata=metadata,
    )

    # Create position
    position = Position(
        id=PositionId(uuid4()),
        strategy_id=strategy_id,
        provider_id=provider_id,
        symbol=symbol,
        side=PositionSide.LONG,
        quantity=quantity,
        average_price=current_price,
        opened_at=utc_now(),
    )

    return order, position


async def _execute_sell_order(
    strategy_id: StrategyId,
    provider_id: ProviderId,
    symbol: str,
    shares: int,
    current_price: Decimal,
    rationale: str = "",
) -> Order:
    """Execute a SELL order (short position)."""
    quantity = Decimal(str(abs(shares)))

    # Build metadata with rationale
    key = build_order_idempotency_key(
        strategy_id,
        provider_id,
        symbol,
        OrderAction.SELL,
        quantity,
        current_price,
    )
    metadata = {"idempotency_key": key}
    if rationale:
        metadata["rationale"] = rationale

    # Create sell order
    order = Order(
        id=OrderId(uuid4()),
        strategy_id=strategy_id,
        provider_id=provider_id,
        symbol=symbol,
        action=OrderAction.SELL,
        quantity=quantity,
        limit_price=current_price,
        status=OrderStatus.FILLED,
        placed_at=utc_now(),
        filled_at=utc_now(),
        metadata=metadata,
    )

    # Create short position
    position = Position(
        id=PositionId(uuid4()),
        strategy_id=strategy_id,
        provider_id=provider_id,
        symbol=symbol,
        side=PositionSide.SHORT,
        quantity=quantity,
        average_price=current_price,
        opened_at=utc_now(),
    )

    return order, position


async def _apply_strategy_recommendations(
    strategy_result: dict,
    initial_balance: Decimal,
    use_live_prices: bool,
) -> dict:
    """Apply recommendations for a single strategy."""
    strategy_id = StrategyId(UUID(strategy_result["strategy_id"]))
    strategy_name = strategy_result["strategy_name"]
    recommendations = strategy_result["recommendations"]

    print(f"\n{'='*80}")
    print(f"Applying: {strategy_name}")
    print(f"Strategy ID: {strategy_id}")
    print(f"Recommendations: {len(recommendations)}")
    print(f"{'='*80}")

    # Use claude_inline as provider
    provider_id = ProviderId.ANTHROPIC

    # Initialize portfolio
    account = await _initialize_portfolio_account(
        strategy_id,
        provider_id,
        initial_balance,
    )

    # Process recommendations
    orders_created = []
    positions_created = []
    container = get_container()

    lookback_cutoff = utc_now() - timedelta(days=7)

    async with container.unit_of_work_factory() as uow:
        for rec in recommendations:
            symbol = rec.get("ticker")
            action = rec.get("action", "").upper()
            shares = rec.get("shares", 0)
            rationale = rec.get("rationale", "")

            if not symbol or shares == 0:
                print(f"  ⏭️  Skipping {symbol} - {action} (0 shares)")
                continue

            print(f"\n  Processing {symbol}: {action} ({shares} shares)")

            # Get price
            if use_live_prices and get_current_price is not None:
                try:
                    current_price = await get_current_price(symbol)
                    print(f"    Live price: ${current_price}")
                except ValueError as e:
                    print(f"    ⚠️  Error fetching price: {e}")
                    # Fallback to recommendation price if available
                    current_price = Decimal(str(rec.get("price", 100.0)))
                    print(f"    Using recommendation price: ${current_price}")
            else:
                current_price = Decimal(str(rec.get("price", 100.0)))
                print(f"    Using recommendation price: ${current_price}")

            if action == "BUY":
                order, position = await _execute_buy_order(
                    strategy_id,
                    provider_id,
                    symbol,
                    shares,
                    current_price,
                    rationale,
                )

                added = await add_order_if_new(
                    uow.order_repository,
                    order,
                    lookback_cutoff=lookback_cutoff,
                )
                if not added:
                    print("    ⚠️  Duplicate BUY detected; skipping order/position")
                    continue

                await uow.position_repository.add(position)

                orders_created.append(order)
                positions_created.append(position)

                cost = order.quantity * order.limit_price
                print(f"    ✓ BUY: {order.quantity} shares @ ${order.limit_price} = ${cost:,.2f}")

            elif action == "SELL":
                order, position = await _execute_sell_order(
                    strategy_id,
                    provider_id,
                    symbol,
                    shares,
                    current_price,
                    rationale,
                )

                added = await add_order_if_new(
                    uow.order_repository,
                    order,
                    lookback_cutoff=lookback_cutoff,
                )
                if not added:
                    print("    ⚠️  Duplicate SELL detected; skipping order/position")
                    continue

                await uow.position_repository.add(position)

                orders_created.append(order)
                positions_created.append(position)

                proceeds = order.quantity * order.limit_price
                print(f"    ✓ SELL: {order.quantity} shares @ ${order.limit_price} = ${proceeds:,.2f}")

            elif action == "HOLD":
                print("    ⏸️  HOLD - no action taken")

        # Update portfolio account
        total_cost = sum(
            order.quantity * order.limit_price
            for order in orders_created
            if order.action == OrderAction.BUY
        )
        total_proceeds = sum(
            order.quantity * order.limit_price
            for order in orders_created
            if order.action == OrderAction.SELL
        )
        total_equity = sum(
            position.quantity * position.average_price
            for position in positions_created
            if position.side == PositionSide.LONG
        )

        updated_account = account.model_copy(
            update={
                "cash_balance": account.cash_balance - total_cost + total_proceeds,
                "equity_value": account.equity_value + total_equity,
                "updated_at": utc_now(),
            }
        )
        await uow.portfolio_repository.upsert(updated_account)

        await uow.commit()

    # Summary
    print("\n  Summary:")
    print(f"    Orders: {len(orders_created)}")
    print(f"    Positions: {len(positions_created)}")
    print(f"    Cash: ${updated_account.cash_balance:,.2f}")
    print(f"    Equity: ${updated_account.equity_value:,.2f}")
    print(f"    Total: ${updated_account.cash_balance + updated_account.equity_value:,.2f}")

    return {
        "strategy_id": str(strategy_id),
        "strategy_name": strategy_name,
        "orders_created": len(orders_created),
        "positions_created": len(positions_created),
        "total_cost": float(total_cost),
        "total_proceeds": float(total_proceeds),
        "cash_balance": float(updated_account.cash_balance),
        "equity_value": float(updated_account.equity_value),
    }


async def _apply_all_recommendations(
    results_file: Path,
    initial_balance: float,
    use_live_prices: bool,
) -> None:
    """Apply all recommendations from inline results file."""
    # Load results
    with open(results_file) as f:
        results = json.load(f)

    print(f"\n{'='*80}")
    print("APPLYING RECOMMENDATIONS TO PORTFOLIOS")
    print(f"{'='*80}")
    print(f"Results file: {results_file}")
    print(f"Strategies: {len(results)}")
    print(f"Initial balance per strategy: ${initial_balance:,.2f}")
    print(f"Live prices: {use_live_prices}")

    initial_balance_decimal = Decimal(str(initial_balance))

    # Process each strategy
    summaries = []
    for strategy_result in results:
        if strategy_result.get("status") != "success":
            print(f"\n⏭️  Skipping {strategy_result['strategy_name']} - status: {strategy_result.get('status')}")
            continue

        try:
            summary = await _apply_strategy_recommendations(
                strategy_result,
                initial_balance_decimal,
                use_live_prices,
            )
            summaries.append(summary)
        except Exception as e:
            print(f"\n❌ Error applying {strategy_result['strategy_name']}: {e}")
            import traceback
            traceback.print_exc()

    # Final summary
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    print(f"Strategies processed: {len(summaries)}")
    print(f"Total orders: {sum(s['orders_created'] for s in summaries)}")
    print(f"Total positions: {sum(s['positions_created'] for s in summaries)}")
    print(f"Total invested: ${sum(s['total_cost'] for s in summaries):,.2f}")
    print(f"Total proceeds: ${sum(s['total_proceeds'] for s in summaries):,.2f}")
    print("\nPer-Strategy Breakdown:")
    for s in summaries:
        print(f"  • {s['strategy_name']}")
        print(f"    Orders: {s['orders_created']}, Positions: {s['positions_created']}")
        print(f"    Cash: ${s['cash_balance']:,.2f}, Equity: ${s['equity_value']:,.2f}")
    print(f"{'='*80}")


@app.command()
def run(
    results_file: str = typer.Argument(
        "artifacts/execute_10_random_inline_results.json",
        help="Path to inline results JSON file"
    ),
    initial_balance: float = typer.Option(100000.0, help="Initial balance per strategy"),
    live_prices: bool = typer.Option(False, help="Use live market prices from Yahoo Finance"),
) -> None:
    """Apply inline recommendations to strategy portfolios."""
    results_path = Path(results_file)
    if not results_path.exists():
        typer.echo(f"Error: Results file not found: {results_file}", err=True)
        raise typer.Exit(code=1)

    asyncio.run(_apply_all_recommendations(results_path, initial_balance, live_prices))


if __name__ == "__main__":
    app()
