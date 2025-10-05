"""Typer CLI wiring Folios v2 services."""

from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import typer

from folios_v2.domain import Strategy, StrategyId, StrategyStatus
from folios_v2.orchestration import StrategyCoordinator

from .deps import get_container

app = typer.Typer(help="Folios v2 command-line interface")


@app.command("show-settings")
def show_settings() -> None:
    """Print the resolved application settings."""

    container = get_container()
    settings = container.settings
    typer.echo("Environment:\t" + settings.environment)
    typer.echo("Database URL:\t" + settings.database_url)
    typer.echo("Artifacts Root:\t" + str(settings.artifacts_root))


@app.command("seed-strategy")
def seed_strategy(
    name: str,
    prompt: str,
    tickers: str = typer.Option(..., help="Comma separated tickers"),
    research_day: int = typer.Option(4, min=1, max=5),
) -> None:
    """Create a strategy in the current persistence layer."""

    container = get_container()
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name=name,
        prompt=prompt,
        tickers=tuple(ticker.strip().upper() for ticker in tickers.split(",")),
        status=StrategyStatus.ACTIVE,
        research_day=research_day,
    )

    async def _persist() -> None:
        async with container.unit_of_work_factory() as uow:
            await uow.strategy_repository.upsert(strategy)
            await uow.commit()

    asyncio.run(_persist())
    typer.echo(f"Created strategy {strategy.id}")


@app.command("list-strategies")
def list_strategies() -> None:
    """List active strategies."""

    container = get_container()

    async def _run() -> None:
        async with container.unit_of_work_factory() as uow:
            strategies = await uow.strategy_repository.list_active()
            if not strategies:
                typer.echo("No strategies found")
                return
            for strategy in strategies:
                typer.echo(f"{strategy.id}\t{strategy.name}\tDay {strategy.research_day}")

    asyncio.run(_run())


@app.command("plan-week")
def plan_week(year: int, week: int) -> None:
    """Ensure weekly runs exist for the specified ISO week."""

    container = get_container()
    coordinator: StrategyCoordinator = container.strategy_coordinator

    async def _run() -> None:
        created = await coordinator.ensure_weekly_runs((year, week))
        typer.echo(f"Created {len(created)} new strategy runs")

    asyncio.run(_run())


@app.command("ensure-schedule")
def ensure_schedule(strategy_id: str) -> None:
    """Ensure a strategy has a schedule entry and display the weekday."""

    container = get_container()
    coordinator: StrategyCoordinator = container.strategy_coordinator

    async def _run() -> None:
        target_id = StrategyId(UUID(strategy_id))
        async with container.unit_of_work_factory() as uow:
            strategy = await uow.strategy_repository.get(target_id)
        if strategy is None:
            typer.echo(f"Strategy {strategy_id} not found")
            raise typer.Exit(code=1)
        schedule = await coordinator.ensure_schedule(strategy)
        typer.echo(f"Strategy {strategy.name} scheduled for weekday {schedule.weekday}")

    asyncio.run(_run())
