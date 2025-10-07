"""Execute portfolio recommendations by creating orders and positions."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from pathlib import Path
from uuid import UUID, uuid4

import typer

from folios_v2.cli.deps import get_container
from folios_v2.domain import Order, Position, PortfolioAccount
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.trading import OrderAction, OrderStatus, PositionSide
from folios_v2.domain.types import OrderId, PositionId, StrategyId
from folios_v2.market_data import get_current_price
from folios_v2.utils import utc_now

app = typer.Typer(help="Execute portfolio recommendations from research requests")


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
            typer.echo(f"Created portfolio account with ${initial_balance:,.2f} initial balance")
        else:
            typer.echo(
                f"Using existing portfolio account: "
                f"cash=${account.cash_balance:,.2f}, equity=${account.equity_value:,.2f}"
            )
    return account


async def _load_recommendations(artifact_dir: Path) -> dict[str, object]:
    """Load recommendations from structured.json or parsed.json."""
    structured_path = artifact_dir / "structured.json"
    parsed_path = artifact_dir / "parsed.json"

    if structured_path.exists():
        data = json.loads(structured_path.read_text(encoding="utf-8"))
        typer.echo(f"Loaded recommendations from {structured_path}")
    elif parsed_path.exists():
        data = json.loads(parsed_path.read_text(encoding="utf-8"))
        typer.echo(f"Loaded recommendations from {parsed_path}")
    else:
        typer.echo(f"No recommendation files found in {artifact_dir}", err=True)
        raise typer.Exit(code=1)

    return data


async def _execute_buy_order(
    strategy_id: StrategyId,
    provider_id: ProviderId,
    symbol: str,
    allocation_percent: float,
    portfolio_value: Decimal,
    current_price: Decimal,
) -> tuple[Order, Position]:
    """Execute a BUY order and create/update position."""
    # Calculate position size
    allocation_amount = portfolio_value * Decimal(str(allocation_percent / 100))
    quantity = (allocation_amount / current_price).quantize(Decimal("0.01"))

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


async def _execute_recommendations(
    request_id: str,
    strategy_id: str,
    provider_id: str,
    initial_balance: float,
    use_live_prices: bool,
) -> None:
    """Execute recommendations for a research request."""
    container = get_container()

    # Parse IDs
    strategy_uuid = StrategyId(UUID(strategy_id))
    provider_enum = ProviderId(provider_id)
    initial_balance_decimal = Decimal(str(initial_balance))

    # Find artifact directory
    artifacts_root = container.settings.artifacts_root
    artifact_dir = artifacts_root / request_id

    # Find task directory (should be only one for single-task requests)
    task_dirs = list(artifact_dir.glob("*"))
    if not task_dirs:
        typer.echo(f"No task directories found in {artifact_dir}", err=True)
        raise typer.Exit(code=1)

    task_dir = task_dirs[0]  # Use first task directory
    typer.echo(f"Using artifact directory: {task_dir}")

    # Load recommendations
    data = await _load_recommendations(task_dir)
    recommendations = data.get("recommendations", [])

    if not recommendations:
        typer.echo("No recommendations found in the data", err=True)
        raise typer.Exit(code=1)

    typer.echo(f"Found {len(recommendations)} recommendations")

    # Initialize portfolio account
    account = await _initialize_portfolio_account(
        strategy_uuid,
        provider_enum,
        initial_balance_decimal,
    )

    # Calculate total portfolio value
    portfolio_value = account.cash_balance + account.equity_value

    # Process recommendations
    orders_created = []
    positions_created = []

    async with container.unit_of_work_factory() as uow:
        for rec in recommendations:
            symbol = rec.get("ticker")
            action = rec.get("action", "").upper()
            # Support both field names: allocation_percent (Anthropic/Gemini) and position_size_pct (OpenAI)
            allocation_percent = rec.get("allocation_percent") or rec.get("position_size_pct", 0)

            if not symbol:
                typer.echo(f"Skipping recommendation with no ticker: {rec}", err=True)
                continue

            typer.echo(f"\nProcessing {symbol}: {action} ({allocation_percent}% allocation)")

            if action == "BUY":
                # Fetch current market price
                if use_live_prices:
                    typer.echo(f"  Fetching live price for {symbol}...")
                    try:
                        current_price = await get_current_price(symbol)
                        typer.echo(f"  Current price: ${current_price}")
                    except ValueError as e:
                        typer.echo(f"  Error fetching price: {e}", err=True)
                        typer.echo(f"  Skipping {symbol}", err=True)
                        continue
                else:
                    # Simulation mode: use a default price
                    current_price = Decimal("100.00")
                    typer.echo(f"  Using simulation price: ${current_price}")

                order, position = await _execute_buy_order(
                    strategy_uuid,
                    provider_enum,
                    symbol,
                    allocation_percent,
                    portfolio_value,
                    current_price,
                )

                await uow.order_repository.add(order)
                await uow.position_repository.add(position)

                orders_created.append(order)
                positions_created.append(position)

                cost = order.quantity * order.limit_price
                typer.echo(
                    f"  Created BUY order: {order.quantity} shares @ ${order.limit_price} = ${cost:,.2f}"
                )
                typer.echo(f"  Created position: {position.id}")

            elif action == "HOLD":
                typer.echo(f"  HOLD action - no order created")

            elif action == "SELL":
                # For SELL, we'd need to find existing position
                # For now, just log it
                typer.echo(f"  SELL action - not yet implemented (requires existing position)")

            else:
                typer.echo(f"  Unknown action: {action}", err=True)

        # Update portfolio account
        total_invested = sum(
            order.quantity * order.limit_price for order in orders_created
        )
        total_equity = sum(
            position.quantity * position.average_price for position in positions_created
        )

        updated_account = account.model_copy(
            update={
                "cash_balance": account.cash_balance - total_invested,
                "equity_value": account.equity_value + total_equity,
                "updated_at": utc_now(),
            }
        )
        await uow.portfolio_repository.upsert(updated_account)

        await uow.commit()

    # Summary
    typer.echo(f"\n{'='*60}")
    typer.echo("Execution Summary")
    typer.echo(f"{'='*60}")
    typer.echo(f"Orders created: {len(orders_created)}")
    typer.echo(f"Positions created: {len(positions_created)}")
    typer.echo(f"Total invested: ${total_invested:,.2f}")
    typer.echo(f"Remaining cash: ${updated_account.cash_balance:,.2f}")
    typer.echo(f"Total equity: ${updated_account.equity_value:,.2f}")
    typer.echo(f"Total portfolio value: ${updated_account.cash_balance + updated_account.equity_value:,.2f}")
    typer.echo(f"{'='*60}")


@app.command()
def run(
    request_id: str = typer.Argument(..., help="Research request ID"),
    strategy_id: str = typer.Argument(..., help="Strategy ID"),
    provider_id: str = typer.Option("anthropic", help="Provider ID"),
    initial_balance: float = typer.Option(100000.0, help="Initial portfolio balance"),
    live_prices: bool = typer.Option(True, help="Use live market prices from Yahoo Finance"),
) -> None:
    """Execute portfolio recommendations from a research request."""
    asyncio.run(
        _execute_recommendations(
            request_id,
            strategy_id,
            provider_id,
            initial_balance,
            live_prices,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    app()
