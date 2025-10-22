#!/usr/bin/env python3
"""Apply recommendations from ANTHROPIC_RECOMMENDATIONS.md to portfolios."""

import asyncio
import re
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
from folios_v2.market_data import get_current_price
from folios_v2.utils import utc_now
from folios_v2.utils.order_idempotency import add_order_if_new, build_order_idempotency_key

app = typer.Typer(help="Apply Anthropic recommendations from markdown")


# Strategy ID mapping from ANTHROPIC_RECOMMENDATIONS.md
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
    # Friday strategies (weekday 5)
    "Ray Dalio Pure Alpha Strategy": "ce7ba1fb-6235-41cb-9063-3622427d21ac",
    "Ray Dalio Strategy": "18e0f836-2541-49a9-b7b0-243a9cc7ff0d",
    "Scuttlebutt Qualitative Research": "740c31df-eb4e-4cba-ac4a-f6560c49ee35",
    "Seth Klarman Strategy": "273a2890-a72f-4c78-8941-0a832b7f0875",
    "Short Selling Overvalued Stocks": "037d907b-393c-46ed-a332-0a11b3744494",
    "Short-Selling Contrarian": "ae281888-8e7c-467d-ba5d-43524dc83824",
    "Stanley Druckenmiller Strategy": "70fd7d10-3fc0-441e-94ac-5757416f659d",
    "Steven Cohen Strategy": "5d8109fa-c277-4d5d-8670-523391e824ba",
    "Terry Smith Strategy": "cccaec95-9e47-4dc7-a251-d70bfe9ce022",
    "Thomas Rowe Price Jr Strategy": "1b34a9b6-4cb9-4e6b-9a31-fd666f63dd6c",
    "Value": "f0ddf4e2-c9a8-4afe-a302-c21f7bc16a70",
    "Value Investing": "0e3f8964-5f16-475a-8e74-e474c4634be7",
    "Walter Schloss Strategy": "c9ff2972-cad7-4359-9e02-9bff4e4f4664",
    "Warren Buffett Quality Growth Strategy": "9a089867-8137-45ed-8a7f-f735f83e0190",
    "Warren Buffett Strategy": "b99a340b-f51e-46ab-9335-ce3a0a3441f3",
    "William O'Neil Strategy": "3d41ab75-db89-40b8-9d55-1ebd094c440d",
    # Manual analysis strategies
    "Cathie Wood Strategy": "4e31e308-adb2-4e9f-bd29-6be510d5b4f7",
    "Charles Brandes Strategy": "42ccd1a7-e47e-4b47-aab2-9417ede4f0b3",
    "Christopher Browne Strategy": "8b5ab2d0-d664-4e47-b437-ed25fed7cbf5",
    "Cigar-Butt Deep Value": "68b86a90-3ac3-4253-985b-0dde7f493e11",
}


def parse_recommendations_from_markdown(md_path: Path) -> dict[str, list[dict]]:
    """Parse recommendations from ANTHROPIC_RECOMMENDATIONS.md."""
    content = md_path.read_text()

    strategy_recommendations = {}

    # Parse each strategy section
    strategy_sections = re.split(r'###\s+Strategy\s+\d+:', content)

    for section in strategy_sections[1:]:  # Skip the header
        lines = section.strip().split('\n')

        # Extract strategy name
        strategy_name = lines[0].strip()

        # Find recommendations section
        in_recommendations = False
        recommendations = []

        for i, line in enumerate(lines):
            if line.strip() == "**Recommendations:**":
                in_recommendations = True
                continue

            if in_recommendations:
                # Format 1: Multi-line structured format (e.g., 1. **INTC (Intel Corporation)**)
                ticker_match = re.match(r'\d+\.\s+\*\*([A-Z\.]+)\s+\((.+?)\)\*\*', line.strip())

                # Format 2: Single-line format (e.g., 1. **USB (U.S. Bancorp)** - Current...)
                single_line_match = re.match(
                    r'\d+\.\s+\*\*([A-Z\.]+)\s+\((.+?)\)\*\*\s+-\s+(.+?)[\.\s]+BUY\s+(\d+)%',
                    line.strip()
                )

                if ticker_match:
                    ticker = ticker_match.group(1)
                    company = ticker_match.group(2)

                    # Extract details from following lines
                    rec_data = {
                        "ticker": ticker,
                        "company": company,
                        "action": "BUY",  # Default
                        "allocation_percent": 0.0,
                        "rationale": "",
                    }

                    # Look ahead for details
                    j = i + 1
                    while j < len(lines) and not lines[j].strip().startswith(('**Overall', '---', '##', '###', '1.', '2.', '3.', '4.')):
                        detail_line = lines[j].strip()

                        # Extract action
                        if detail_line.startswith("*   **Action:**"):
                            action_match = re.search(r'\*\*Action:\*\*\s+(\w+)', detail_line)
                            if action_match:
                                rec_data["action"] = action_match.group(1)

                        # Extract position size
                        elif detail_line.startswith("*   **Position Size:**"):
                            size_match = re.search(r'(\d+(?:\.\d+)?)-?(\d+(?:\.\d+)?)?%', detail_line)
                            if size_match:
                                # Use midpoint if range, otherwise use single value
                                if size_match.group(2):
                                    rec_data["allocation_percent"] = (
                                        float(size_match.group(1)) + float(size_match.group(2))
                                    ) / 2
                                else:
                                    rec_data["allocation_percent"] = float(size_match.group(1))

                        # Extract investment thesis (rationale)
                        elif detail_line.startswith("*   **Investment Thesis:**"):
                            thesis = detail_line.replace("*   **Investment Thesis:**", "").strip()
                            rec_data["rationale"] = thesis

                        j += 1

                    if rec_data["allocation_percent"] > 0:
                        recommendations.append(rec_data)

                elif single_line_match:
                    # Single-line format
                    ticker = single_line_match.group(1)
                    company = single_line_match.group(2)
                    rationale = single_line_match.group(3).strip()
                    allocation_percent = float(single_line_match.group(4))

                    recommendations.append({
                        "ticker": ticker,
                        "company": company,
                        "action": "BUY",
                        "allocation_percent": allocation_percent,
                        "rationale": rationale,
                    })

                # Check if we've moved to next section
                elif line.strip().startswith(('**Overall', '---', '## ', '### Strategy')):
                    break
                # Handle special format for corporate raider (sub-bullets)
                elif line.strip().startswith('*   **') and '(' in line and 'BUY' in line:
                    sub_match = re.match(r'\*\s+\*\*([A-Z\.]+)\s+\((.+?)\)\*\*\s+-\s+(.+?)[\.\s]+BUY\s+(\d+)%', line.strip())
                    if sub_match:
                        ticker = sub_match.group(1)
                        company = sub_match.group(2)
                        rationale = sub_match.group(3).strip()
                        allocation_percent = float(sub_match.group(4))

                        recommendations.append({
                            "ticker": ticker,
                            "company": company,
                            "action": "BUY",
                            "allocation_percent": allocation_percent,
                            "rationale": rationale,
                        })

        if recommendations:
            strategy_recommendations[strategy_name] = recommendations

    return strategy_recommendations


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
    allocation_percent: float,
    portfolio_value: Decimal,
    current_price: Decimal,
    rationale: str = "",
) -> tuple[Order, Position]:
    """Execute a BUY order and create position."""
    # Calculate position size
    allocation_amount = portfolio_value * Decimal(str(allocation_percent / 100))
    quantity = (allocation_amount / current_price).quantize(Decimal("0.01"))

    # Build metadata with rationale
    key = build_order_idempotency_key(
        strategy_uuid,
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


async def _execute_short_order(
    strategy_id: StrategyId,
    provider_id: ProviderId,
    symbol: str,
    allocation_percent: float,
    portfolio_value: Decimal,
    current_price: Decimal,
    rationale: str = "",
) -> tuple[Order, Position]:
    """Execute a SELL_SHORT order and create short position."""
    # Calculate position size
    allocation_amount = portfolio_value * Decimal(str(allocation_percent / 100))
    quantity = (allocation_amount / current_price).quantize(Decimal("0.01"))

    # Build metadata with rationale
    key = build_order_idempotency_key(
        strategy_uuid,
        provider_id,
        symbol,
        OrderAction.SELL_SHORT,
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
        action=OrderAction.SELL_SHORT,
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
    strategy_name: str,
    strategy_id: str,
    recommendations: list[dict],
    initial_balance: Decimal,
    use_live_prices: bool,
) -> dict:
    """Apply recommendations for a single strategy."""
    print(f"\n{'='*80}")
    print(f"Strategy: {strategy_name}")
    print(f"Strategy ID: {strategy_id}")
    print(f"Recommendations: {len(recommendations)}")
    print(f"{'='*80}")

    provider_id = ProviderId.ANTHROPIC
    strategy_uuid = StrategyId(UUID(strategy_id))

    # Initialize portfolio
    account = await _initialize_portfolio_account(
        strategy_uuid,
        provider_id,
        initial_balance,
    )

    portfolio_value = account.cash_balance + account.equity_value

    # Process recommendations
    orders_created = []
    positions_created = []
    container = get_container()

    lookback_cutoff = utc_now() - timedelta(days=7)

    async with container.unit_of_work_factory() as uow:
        for rec in recommendations:
            symbol = rec["ticker"]
            action = rec["action"]
            allocation_percent = rec["allocation_percent"]
            rationale = rec.get("rationale", "")

            print(f"\n  Processing {symbol}: {action} ({allocation_percent}% allocation)")

            if action == "BUY":
                # Get live price
                if use_live_prices:
                    try:
                        current_price = await get_current_price(symbol)
                        print(f"    Live price: ${current_price}")
                    except Exception as e:
                        print(f"    ERROR: Failed to fetch live price for {symbol}: {e}")
                        print(f"    Skipping {symbol}")
                        continue
                else:
                    # Use placeholder price for dry-run
                    current_price = Decimal("100.0")
                    print(f"    Using placeholder price: ${current_price}")

                order, position = await _execute_buy_order(
                    strategy_uuid,
                    provider_id,
                    symbol,
                    allocation_percent,
                    portfolio_value,
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

            elif action == "SHORT":
                # Get live price
                if use_live_prices:
                    try:
                        current_price = await get_current_price(symbol)
                        print(f"    Live price: ${current_price}")
                    except Exception as e:
                        print(f"    ERROR: Failed to fetch live price for {symbol}: {e}")
                        print(f"    Skipping {symbol}")
                        continue
                else:
                    # Use placeholder price for dry-run
                    current_price = Decimal("100.0")
                    print(f"    Using placeholder price: ${current_price}")

                order, position = await _execute_short_order(
                    strategy_uuid,
                    provider_id,
                    symbol,
                    allocation_percent,
                    portfolio_value,
                    current_price,
                    rationale,
                )

                added = await add_order_if_new(
                    uow.order_repository,
                    order,
                    lookback_cutoff=lookback_cutoff,
                )
                if not added:
                    print("    ⚠️  Duplicate SHORT detected; skipping order/position")
                    continue

                await uow.position_repository.add(position)

                orders_created.append(order)
                positions_created.append(position)

                proceeds = order.quantity * order.limit_price
                print(f"    ✓ SHORT: {order.quantity} shares @ ${order.limit_price} = ${proceeds:,.2f}")

            elif action == "HOLD":
                print("    ⏸️  HOLD - no action taken")

        # Update portfolio account
        # For longs: we spend cash to buy (negative), equity increases (positive)
        total_long_cost = sum(
            order.quantity * order.limit_price
            for order in orders_created
            if order.action == OrderAction.BUY
        )
        total_long_equity = sum(
            position.quantity * position.average_price
            for position in positions_created
            if position.side == PositionSide.LONG
        )

        # For shorts: we receive cash proceeds (positive), equity decreases (negative liability)
        total_short_proceeds = sum(
            order.quantity * order.limit_price
            for order in orders_created
            if order.action == OrderAction.SELL_SHORT
        )
        total_short_equity = sum(
            position.quantity * position.average_price
            for position in positions_created
            if position.side == PositionSide.SHORT
        )

        updated_account = account.model_copy(
            update={
                "cash_balance": account.cash_balance - total_long_cost + total_short_proceeds,
                "equity_value": account.equity_value + total_long_equity - total_short_equity,
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

    # Calculate net capital deployed (long cost - short proceeds)
    net_capital_deployed = total_long_cost - total_short_proceeds

    return {
        "strategy_name": strategy_name,
        "strategy_id": strategy_id,
        "orders_created": len(orders_created),
        "positions_created": len(positions_created),
        "net_capital_deployed": float(net_capital_deployed),
        "cash_balance": float(updated_account.cash_balance),
        "equity_value": float(updated_account.equity_value),
    }


async def _apply_all_recommendations(
    md_path: Path,
    initial_balance: float,
    use_live_prices: bool,
) -> None:
    """Apply all recommendations from markdown."""
    print(f"\n{'='*80}")
    print("APPLYING ANTHROPIC RECOMMENDATIONS TO PORTFOLIOS")
    print(f"{'='*80}")
    print(f"Source: {md_path}")
    print(f"Initial balance per strategy: ${initial_balance:,.2f}")
    print(f"Live prices: {use_live_prices}")

    # Parse recommendations
    print("\nParsing recommendations from markdown...")
    strategy_recommendations = parse_recommendations_from_markdown(md_path)
    print(f"Found {len(strategy_recommendations)} strategies with recommendations")

    initial_balance_decimal = Decimal(str(initial_balance))

    # Process each strategy
    summaries = []
    for strategy_name, recommendations in strategy_recommendations.items():
        strategy_id = STRATEGY_MAPPING.get(strategy_name)

        if not strategy_id:
            print(f"\n⏭️  Skipping {strategy_name} - no strategy ID mapping found")
            continue

        if strategy_name == "Benjamin Graham Cigar Butt Strategy":
            print(f"\n⏭️  Skipping {strategy_name} - HOLD CASH recommendation")
            continue

        try:
            summary = await _apply_strategy_recommendations(
                strategy_name,
                strategy_id,
                recommendations,
                initial_balance_decimal,
                use_live_prices,
            )
            summaries.append(summary)
        except Exception as e:
            print(f"\n❌ Error applying {strategy_name}: {e}")
            import traceback
            traceback.print_exc()

    # Final summary
    print(f"\n{'='*80}")
    print("FINAL SUMMARY")
    print(f"{'='*80}")
    print(f"Strategies processed: {len(summaries)}")
    print(f"Total orders: {sum(s['orders_created'] for s in summaries)}")
    print(f"Total positions: {sum(s['positions_created'] for s in summaries)}")
    print(f"Net capital deployed: ${sum(s['net_capital_deployed'] for s in summaries):,.2f}")
    print("\nPer-Strategy Breakdown:")
    for s in summaries:
        print(f"  • {s['strategy_name']}")
        print(f"    Orders: {s['orders_created']}, Positions: {s['positions_created']}")
        print(f"    Cash: ${s['cash_balance']:,.2f}, Equity: ${s['equity_value']:,.2f}")
    print(f"{'='*80}")


@app.command()
def run(
    md_file: str = typer.Argument(
        "ANTHROPIC_RECOMMENDATIONS.md",
        help="Path to markdown file with recommendations"
    ),
    initial_balance: float = typer.Option(100000.0, help="Initial balance per strategy"),
    live_prices: bool = typer.Option(True, help="Use live market prices from Yahoo Finance"),
) -> None:
    """Apply Anthropic recommendations from markdown to strategy portfolios."""
    md_path = Path(md_file)
    if not md_path.exists():
        typer.echo(f"Error: File not found: {md_file}", err=True)
        raise typer.Exit(code=1)

    asyncio.run(_apply_all_recommendations(md_path, initial_balance, live_prices))


if __name__ == "__main__":
    app()
