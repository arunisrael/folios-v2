"""Submit batch research requests for active strategies."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from dotenv import load_dotenv

# Load .env file before importing folios modules
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, RequestPriority, RequestType
from folios_v2.domain.enums import ProviderId
from folios_v2.utils import utc_now

app = typer.Typer(help="Submit batch research requests for strategies")


async def _submit_batch_requests(
    strategy_id: str | None,
    providers: list[str],
) -> None:
    """Submit batch research requests."""
    container = get_container()

    # Parse provider IDs
    provider_ids = [ProviderId(p) for p in providers]

    async with container.unit_of_work_factory() as uow:
        if strategy_id:
            # Submit for specific strategy
            from uuid import UUID

            from folios_v2.domain.types import StrategyId

            sid = StrategyId(UUID(strategy_id))
            strategy = await uow.strategy_repository.get(sid)
            if strategy is None:
                typer.echo(f"Strategy {strategy_id} not found", err=True)
                raise typer.Exit(code=1)
            strategies = [strategy]
        else:
            # Submit for all active strategies
            strategies = await uow.strategy_repository.list_active()

        if not strategies:
            typer.echo("No strategies found")
            return

        typer.echo(f"Submitting batch requests for {len(strategies)} strategy(ies)")

        submitted = []
        for strategy in strategies:
            typer.echo(f"\nStrategy: {strategy.name} ({strategy.id})")

            for provider_id in provider_ids:
                # Check if provider supports batch mode
                try:
                    plugin = container.provider_registry.require(provider_id, ExecutionMode.BATCH)
                except Exception as e:
                    typer.echo(f"  Skipping {provider_id.value}: {e}", err=True)
                    continue

                if not plugin.supports_batch:
                    typer.echo(f"  Skipping {provider_id.value}: batch mode not supported")
                    continue

                # Enqueue the request
                request, task = await container.request_orchestrator.enqueue_request(
                    strategy,
                    provider_id=provider_id,
                    request_type=RequestType.RESEARCH,
                    mode=ExecutionMode.BATCH,
                    priority=RequestPriority.NORMAL,
                    scheduled_for=utc_now(),
                    metadata={"triggered_by": "batch_submission_script"},
                )

                typer.echo(
                    f"  ✓ {provider_id.value}: request_id={request.id}, task_id={task.id}"
                )
                submitted.append((strategy, provider_id, request, task))

        await uow.commit()

    typer.echo(f"\n{'='*60}")
    typer.echo(f"Total batch requests submitted: {len(submitted)}")
    typer.echo(f"{'='*60}")


@app.command()
def run(
    strategy_id: str | None = typer.Option(
        None, help="Strategy ID (omit to submit for all active strategies)"
    ),
    providers: str = typer.Option(
        "openai,gemini", help="Comma-separated provider IDs (openai, gemini, anthropic)"
    ),
) -> None:
    """Submit batch research requests for strategies."""
    provider_list = [p.strip() for p in providers.split(",")]
    asyncio.run(_submit_batch_requests(strategy_id, provider_list))


if __name__ == "__main__":  # pragma: no cover
    app()
