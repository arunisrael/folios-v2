"""Execute portfolio recommendations by creating orders and positions."""

from __future__ import annotations

import asyncio
import json
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
    rationale: str = "",
) -> tuple[Order, Position]:
    """Execute a BUY order and create/update position."""
    # Calculate position size
    allocation_amount = portfolio_value * Decimal(str(allocation_percent / 100))
    quantity = (allocation_amount / current_price).quantize(Decimal("0.01"))

    # Build metadata with rationale
    metadata = {}
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


async def _execute_sell_short_order(
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
    metadata = {}
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


async def _execute_recommendations(
    request_id: str,
    strategy_id: str,
    provider_id: str,
    initial_balance: float,
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
            # Support both field names: allocation_percent (Anthropic/Gemini)
            # and position_size_pct (OpenAI)
            allocation_percent = rec.get("allocation_percent") or rec.get(
                "position_size_pct", 0
            )
            rationale = rec.get("rationale", "")

            if not symbol:
                typer.echo(f"Skipping recommendation with no ticker: {rec}", err=True)
                continue

            typer.echo(f"\nProcessing {symbol}: {action} ({allocation_percent}% allocation)")

            if action == "BUY":
                # ALWAYS fetch live price from Yahoo Finance
                typer.echo(f"  Fetching live price for {symbol}...")
                try:
                    current_price = await get_current_price(symbol)
                    typer.echo(f"  Live price: ${current_price}")
                except ValueError as e:
                    typer.echo(f"  ERROR: Failed to fetch live price for {symbol}: {e}", err=True)
                    typer.echo(f"  Skipping {symbol} - cannot execute without live price", err=True)
                    continue

                order, position = await _execute_buy_order(
                    strategy_uuid,
                    provider_enum,
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
                typer.echo(
                    f"  Created BUY order: {order.quantity} shares @ "
                    f"${order.limit_price} = ${cost:,.2f}"
                )
                typer.echo(f"  Created position: {position.id}")

            elif action == "SELL_SHORT":
                # ALWAYS fetch live price from Yahoo Finance
                typer.echo(f"  Fetching live price for {symbol}...")
                try:
                    current_price = await get_current_price(symbol)
                    typer.echo(f"  Live price: ${current_price}")
                except ValueError as e:
                    typer.echo(f"  ERROR: Failed to fetch live price for {symbol}: {e}", err=True)
                    typer.echo(f"  Skipping {symbol} - cannot execute without live price", err=True)
                    continue

                order, position = await _execute_sell_short_order(
                    strategy_uuid,
                    provider_enum,
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

                proceeds = order.quantity * order.limit_price
                typer.echo(
                    f"  Created SELL_SHORT order: {order.quantity} shares @ "
                    f"${order.limit_price} = ${proceeds:,.2f}"
                )
                typer.echo(f"  Created short position: {position.id}")

            elif action == "HOLD":
                typer.echo("  HOLD action - no order created")

            elif action == "SELL":
                # For SELL, we'd need to find existing position
                # For now, just log it
                typer.echo("  SELL action - not yet implemented (requires existing position)")

            else:
                typer.echo(f"  Unknown action: {action}", err=True)

        # Update portfolio account
        # Calculate cash changes: BUY decreases cash, SELL_SHORT increases cash
        cash_delta = Decimal("0")
        for order in orders_created:
            order_value = order.quantity * order.limit_price
            if order.action == OrderAction.BUY:
                cash_delta -= order_value
            elif order.action == OrderAction.SELL_SHORT:
                cash_delta += order_value

        # Calculate equity: LONG positions are assets (+), SHORT positions are liabilities (-)
        equity_delta = Decimal("0")
        for position in positions_created:
            position_value = position.quantity * position.average_price
            if position.side == PositionSide.LONG:
                equity_delta += position_value
            elif position.side == PositionSide.SHORT:
                equity_delta -= position_value

        updated_account = account.model_copy(
            update={
                "cash_balance": account.cash_balance + cash_delta,
                "equity_value": account.equity_value + equity_delta,
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
    typer.echo(f"Cash change: ${cash_delta:,.2f}")
    typer.echo(f"Cash balance: ${updated_account.cash_balance:,.2f}")
    typer.echo(f"Equity value: ${updated_account.equity_value:,.2f} (long + short liabilities)")
    portfolio_value = updated_account.cash_balance + updated_account.equity_value
    typer.echo(f"Total portfolio value: ${portfolio_value:,.2f}")
    typer.echo(f"{'='*60}")


@app.command()
def run(
    request_id: str = typer.Argument(..., help="Research request ID"),
    strategy_id: str = typer.Argument(..., help="Strategy ID"),
    provider_id: str = typer.Option("anthropic", help="Provider ID"),
    initial_balance: float = typer.Option(100000.0, help="Initial portfolio balance"),
) -> None:
    """Execute portfolio recommendations from a research request.

    Note: Always fetches live prices from Yahoo Finance. No simulation mode.
    """
    asyncio.run(
        _execute_recommendations(
            request_id,
            strategy_id,
            provider_id,
            initial_balance,
        )
    )


if __name__ == "__main__":  # pragma: no cover
    app()
