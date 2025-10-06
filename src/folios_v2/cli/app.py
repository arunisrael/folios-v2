"""Typer CLI wiring Folios v2 services."""

from __future__ import annotations

import asyncio
import json
from uuid import UUID, uuid4

import typer

from folios_v2.domain import (
    ScreenerProviderId,
    Strategy,
    StrategyId,
    StrategyScreener,
    StrategyStatus,
)
from folios_v2.orchestration import StrategyCoordinator
from folios_v2.screeners import ScreenerError, ScreenerResult

from .deps import get_container

app = typer.Typer(help="Folios v2 command-line interface")
screener_app = typer.Typer(help="Stock screener utilities")
app.add_typer(screener_app, name="screener")


def _parse_strategy_id(value: str) -> StrategyId:
    try:
        return StrategyId(UUID(value))
    except ValueError as exc:
        raise typer.BadParameter("strategy-id must be a valid UUID") from exc


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


@screener_app.command("run")
def screener_run(
    strategy_id: str,
    provider: str | None = typer.Option(None, help="Override screener provider id"),
    limit: int | None = typer.Option(None, min=1, help="Override screener limit"),
) -> None:
    """Execute a screener and show the resulting candidates."""

    container = get_container()
    service = container.screener_service
    if not service.available_providers():
        typer.echo("No screener providers are configured in this environment")
        raise typer.Exit(code=1)

    target_id = _parse_strategy_id(strategy_id)

    provider_id: ScreenerProviderId | None = None
    if provider is not None:
        try:
            provider_id = ScreenerProviderId(provider.lower())
        except ValueError as exc:
            choices = ", ".join(p.value for p in service.available_providers()) or "none"
            typer.echo(f"Unsupported screener provider '{provider}'. Available: {choices}")
            raise typer.Exit(code=1) from exc

    async def _run() -> tuple[Strategy, StrategyScreener, ScreenerResult, bool]:
        async with container.unit_of_work_factory() as uow:
            strategy = await uow.strategy_repository.get(target_id)
            if strategy is None:
                raise LookupError(f"Strategy {strategy_id} not found")
            if strategy.screener is None:
                raise ValueError("Strategy has no screener configuration")

            overrides: dict[str, object] = {}
            if provider_id is not None:
                overrides["provider"] = provider_id
            if limit is not None:
                overrides["limit"] = limit

            config = (
                strategy.screener
                if not overrides
                else strategy.screener.model_copy(update=overrides)
            )

            result = await service.run(config)

            updated_strategy = strategy
            tickers_changed = False
            if result.symbols and tuple(result.symbols) != strategy.tickers:
                updated_strategy = strategy.model_copy(update={"tickers": tuple(result.symbols)})
                await uow.strategy_repository.upsert(updated_strategy)
                tickers_changed = True

            await uow.commit()
            return updated_strategy, config, result, tickers_changed

    try:
        strategy_after, config_used, result, tickers_changed = asyncio.run(_run())
    except LookupError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(code=1) from exc
    except ScreenerError as exc:
        typer.echo(f"Screener execution failed: {exc}")
        raise typer.Exit(code=1) from exc

    candidates = ", ".join(result.symbols) if result.symbols else "(none)"
    typer.echo(f"Provider: {result.provider.value}")
    typer.echo(f"Candidates ({len(result.symbols)}): {candidates}")
    typer.echo("Filters: " + json.dumps(config_used.filters, sort_keys=True))
    if tickers_changed:
        refreshed = ", ".join(strategy_after.tickers) if strategy_after.tickers else "(none)"
        typer.echo("Strategy tickers updated to: " + refreshed)


@screener_app.command("inspect")
def screener_inspect(strategy_id: str) -> None:
    """Display the stored screener configuration for a strategy."""

    container = get_container()
    target_id = _parse_strategy_id(strategy_id)

    async def _run() -> Strategy | None:
        async with container.unit_of_work_factory() as uow:
            strategy = await uow.strategy_repository.get(target_id)
            await uow.commit()
        return strategy

    strategy = asyncio.run(_run())
    if strategy is None:
        typer.echo(f"Strategy {strategy_id} not found")
        raise typer.Exit(code=1)

    typer.echo(f"Strategy: {strategy.name}")
    typer.echo(
        "Tickers: " + (", ".join(strategy.tickers) if strategy.tickers else "(none)")
    )
    config = strategy.screener
    if config is None:
        typer.echo("Screener: not configured")
        return

    typer.echo(f"Screener provider: {config.provider.value}")
    typer.echo(f"Enabled: {config.enabled}")
    typer.echo(f"Limit: {config.limit}")
    if config.universe_cap is not None:
        typer.echo(f"Universe cap: {config.universe_cap}")
    typer.echo("Filters:\n" + json.dumps(config.filters, indent=2, sort_keys=True))
