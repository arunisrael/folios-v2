#!/usr/bin/env python3
"""Execute remaining Anthropic strategies from parsed recommendations."""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

from folios_v2.cli.deps import get_container
from folios_v2.domain import Order, PortfolioAccount, Position
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.trading import OrderAction, OrderStatus, PositionSide
from folios_v2.domain.types import OrderId, PositionId, StrategyId
from folios_v2.market_data import get_current_price
from folios_v2.utils import utc_now

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))
from parse_anthropic_recs_simple import parse_all_recommendations

# Strategy ID mapping
STRATEGY_MAPPING = {
    "Activist Value Investing": "5bdc6204-72a8-44bf-bbe9-70b26596589b",
    "All Weather Risk Parity": "c4b78c0c-cb0a-4f8f-b800-8646049b047c",
    "Beaten-Down Leaders Strategy": "0f4bf47a-e63c-40d7-8138-e8a5395f5331",
    "Benjamin Graham Cigar Butt Strategy": "6b291794-02b8-471f-b02c-24d78802164f",
    "Benjamin Graham Strategy": "d75d1377-1721-4f1b-852c-f54bb495847a",
    "Bill Ackman Strategy": "e04d2c5d-0811-4441-bd0c-2807446dad1d",
    "Bill Ackman Turnaround Strategy": "926b57d7-cc11-4d0b-a8f8-3391d474163c",
    "Bill Miller Strategy": "0996fc65-e1e7-4a87-87e2-8eea5e5b6396",
    "Bruce Berkowitz Strategy": "bd096507-a4cb-4dc7-832b-1a9519f4ea40",
    "Carl Icahn Corporate Raider Strategy": "08491010-8cb3-4150-abc9-82e128dfbc85",
    "Carl Icahn Strategy": "19ba440a-da27-4819-b691-d3d8cc76ff19",
    "Charlie Munger Quality Compounder Strategy": "62da9866-b395-4d00-8bc5-209cc130901e",
    "Charlie Munger Strategy": "62da9866-b395-4d00-8bc5-209cc130901e",
    "Contrarian Value Investing": "a3a3cfea-d9de-4e9a-bb85-b5517a026c0d",
}

# Strategies already executed
ALREADY_EXECUTED = {
    "Activist Value Investing",
    "All Weather Risk Parity",
    "Beaten-Down Leaders Strategy",
}


async def initialize_portfolio(strategy_id: StrategyId, provider_id: ProviderId, initial_balance: Decimal):
    """Initialize or get portfolio account."""
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
            print(f"  ✓ Created portfolio with ${initial_balance:,.2f}")
        else:
            print(f"  ⚠ Portfolio exists: cash=${account.cash_balance:,.2f}, equity=${account.equity_value:,.2f}")
    return account


async def execute_buy(
    strategy_id: StrategyId,
    provider_id: ProviderId,
    symbol: str,
    allocation_percent: float,
    portfolio_value: Decimal,
    current_price: Decimal,
    rationale: str = "",
):
    """Execute BUY order."""
    allocation_amount = portfolio_value * Decimal(str(allocation_percent / 100))
    quantity = (allocation_amount / current_price).quantize(Decimal("0.01"))

    metadata = {"rationale": rationale} if rationale else {}

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


async def execute_strategy(strategy_name: str, recommendations: list[dict], initial_balance: Decimal):
    """Execute recommendations for a single strategy."""
    strategy_id = STRATEGY_MAPPING.get(strategy_name)

    if not strategy_id:
        print(f"\n⏭  Skipping {strategy_name} - no strategy ID mapping")
        return None

    if strategy_name in ALREADY_EXECUTED:
        print(f"\n⏭  Skipping {strategy_name} - already executed")
        return None

    print(f"\n{'='*80}")
    print(f"Strategy: {strategy_name}")
    print(f"Strategy ID: {strategy_id}")
    print(f"Recommendations: {len(recommendations)}")
    print(f"{'='*80}")

    provider_id = ProviderId.ANTHROPIC
    strategy_uuid = StrategyId(UUID(strategy_id))

    # Initialize portfolio
    account = await initialize_portfolio(strategy_uuid, provider_id, initial_balance)
    portfolio_value = account.cash_balance + account.equity_value

    # Process recommendations
    orders_created = []
    positions_created = []
    skipped = []
    container = get_container()

    async with container.unit_of_work_factory() as uow:
        for rec in recommendations:
            symbol = rec["ticker"]
            allocation_percent = rec["allocation_percent"]
            rationale = rec.get("rationale", "")

            print(f"\n  Processing {symbol}: BUY ({allocation_percent}% allocation)")

            # Get live price
            try:
                current_price = await get_current_price(symbol)
                print(f"    Live price: ${current_price}")
            except Exception as e:
                print(f"    ✗ ERROR: Failed to fetch price - {e}")
                skipped.append(symbol)
                continue

            try:
                order, position = await execute_buy(
                    strategy_uuid,
                    provider_id,
                    symbol,
                    allocation_percent,
                    portfolio_value,
                    current_price,
                    rationale,
                )

                await uow.order_repository.add(order)
                await uow.position_repository.add(position)

                orders_created.append(order)
                positions_created.append(position)

                cost = order.quantity * order.limit_price
                print(f"    ✓ BUY: {order.quantity} shares @ ${order.limit_price} = ${cost:,.2f}")

            except Exception as e:
                print(f"    ✗ ERROR: Failed to create order/position - {e}")
                skipped.append(symbol)
                continue

        # Update portfolio account
        total_cost = sum(
            order.quantity * order.limit_price
            for order in orders_created
            if order.action == OrderAction.BUY
        )
        total_equity = sum(
            position.quantity * position.average_price
            for position in positions_created
            if position.side == PositionSide.LONG
        )

        updated_account = account.model_copy(
            update={
                "cash_balance": account.cash_balance - total_cost,
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
    print(f"    Skipped: {len(skipped)} {skipped if skipped else ''}")
    print(f"    Cash: ${updated_account.cash_balance:,.2f}")
    print(f"    Equity: ${updated_account.equity_value:,.2f}")
    print(f"    Total: ${updated_account.cash_balance + updated_account.equity_value:,.2f}")

    return {
        "strategy_name": strategy_name,
        "strategy_id": strategy_id,
        "orders_created": len(orders_created),
        "positions_created": len(positions_created),
        "skipped": skipped,
        "total_cost": float(total_cost),
        "cash_balance": float(updated_account.cash_balance),
        "equity_value": float(updated_account.equity_value),
    }


async def main():
    """Execute all remaining strategies."""
    print(f"\n{'='*80}")
    print("EXECUTING REMAINING ANTHROPIC RECOMMENDATIONS")
    print(f"{'='*80}")

    # Parse recommendations
    all_recs = parse_all_recommendations()
    print(f"\nParsed {len(all_recs)} strategies with recommendations")

    initial_balance = Decimal("100000.0")

    # Execute each strategy
    summaries = []
    for strategy_name, recommendations in all_recs.items():
        try:
            summary = await execute_strategy(strategy_name, recommendations, initial_balance)
            if summary:
                summaries.append(summary)
        except Exception as e:
            print(f"\n❌ ERROR executing {strategy_name}: {e}")
            import traceback
            traceback.print_exc()

    # Final summary
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    print(f"Strategies executed: {len(summaries)}")
    print(f"Total orders: {sum(s['orders_created'] for s in summaries)}")
    print(f"Total positions: {sum(s['positions_created'] for s in summaries)}")
    print(f"Total invested: ${sum(s['total_cost'] for s in summaries):,.2f}")

    print("\nPer-Strategy Breakdown:")
    for s in summaries:
        print(f"  • {s['strategy_name']}")
        print(f"    Orders: {s['orders_created']}, Positions: {s['positions_created']}")
        if s['skipped']:
            print(f"    Skipped: {', '.join(s['skipped'])}")
        print(f"    Cash: ${s['cash_balance']:,.2f}, Equity: ${s['equity_value']:,.2f}")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
