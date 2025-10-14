#!/usr/bin/env python3
"""Apply recommendations from ANTHROPIC_RECOMMENDATIONS.md to portfolios."""

import asyncio
import re
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
    metadata = {"rationale": rationale} if rationale else {}

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

                await uow.order_repository.add(order)
                await uow.position_repository.add(position)

                orders_created.append(order)
                positions_created.append(position)

                cost = order.quantity * order.limit_price
                print(f"    ✓ BUY: {order.quantity} shares @ ${order.limit_price} = ${cost:,.2f}")

            elif action == "HOLD":
                print("    ⏸️  HOLD - no action taken")

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
    print(f"    Cash: ${updated_account.cash_balance:,.2f}")
    print(f"    Equity: ${updated_account.equity_value:,.2f}")
    print(f"    Total: ${updated_account.cash_balance + updated_account.equity_value:,.2f}")

    return {
        "strategy_name": strategy_name,
        "strategy_id": strategy_id,
        "orders_created": len(orders_created),
        "positions_created": len(positions_created),
        "total_cost": float(total_cost),
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
    print(f"Total invested: ${sum(s['total_cost'] for s in summaries):,.2f}")
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
