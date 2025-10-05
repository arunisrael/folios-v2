"""Submit research requests for strategies that lack recent runs."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import typer

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, RequestPriority, RequestType
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.types import StrategyId
from folios_v2.utils import utc_now

app = typer.Typer(help="Submit research requests for strategies that need fresh runs")


def _stale_cutoff(hours: int) -> datetime:
    return datetime.now(UTC) - timedelta(hours=hours)


async def _submit(max_strategies: int, stale_hours: int) -> None:
    container = get_container()
    cutoff = _stale_cutoff(stale_hours)

    async with container.unit_of_work_factory() as uow:
        strategies = await uow.strategy_repository.list_active()
        pending = await uow.request_repository.list_pending(limit=500)
        pending_map: set[StrategyId] = {StrategyId(req.strategy_id) for req in pending}

    submitted = 0
    for strategy in strategies:
        if submitted >= max_strategies:
            break
        if strategy.id in pending_map:
            continue

        provider_id = ProviderId.OPENAI
        plugin = container.provider_registry.require(provider_id, ExecutionMode.CLI)
        scheduled_for = max(cutoff, utc_now())
        await container.request_orchestrator.enqueue_request(
            strategy,
            provider_id=provider_id,
            request_type=RequestType.RESEARCH,
            mode=plugin.default_mode,
            priority=RequestPriority.HIGH,
            scheduled_for=scheduled_for,
            metadata={"auto_submitted": "true"},
        )
        submitted += 1
        typer.echo(
            f"Submitted research request for strategy {strategy.name} via {provider_id.value}"
        )

    typer.echo(f"Total submissions: {submitted}")


@app.command()
def run(
    max_strategies: int = typer.Option(10, help="Maximum number of strategies to submit"),
    stale_hours: int = typer.Option(24, help="Consider strategies stale after this many hours"),
) -> None:
    """Queue research requests for strategies that have no pending work."""

    asyncio.run(_submit(max_strategies, stale_hours))


if __name__ == "__main__":  # pragma: no cover
    app()
