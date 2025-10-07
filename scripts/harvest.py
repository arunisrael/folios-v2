"""Run a lightweight harvest cycle across pending requests."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import typer
from dotenv import load_dotenv

# Load .env file before importing folios modules
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, LifecycleState
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.utils import utc_now

app = typer.Typer(help="Harvest pending requests by running their tasks once")


async def _process_request(ctx: ExecutionTaskContext) -> dict[str, object]:
    container = get_container()
    registry = container.provider_registry
    plugin = registry.require(ctx.request.provider_id, ctx.request.mode)

    if ctx.request.mode is ExecutionMode.BATCH:
        if plugin.serializer is None or plugin.batch_executor is None:
            raise typer.Exit(code=1)
        await plugin.serializer.serialize(ctx)
        outcome = await container.batch_runtime.run(plugin, ctx)
        parsed = await plugin.parser.parse(ctx)
        parsed["provider_job_id"] = outcome.submit_result.provider_job_id
    else:
        result = await container.cli_runtime.run(plugin, ctx)
        parsed = await plugin.parser.parse(ctx)
        parsed["cli_exit_code"] = result.result.exit_code

    parsed_path = ctx.artifact_dir / "parsed.json"
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    return parsed


async def _harvest(limit: int) -> None:
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        requests = await uow.request_repository.list_pending(limit=limit)
        if not requests:
            typer.echo("No pending requests discovered")
            return

        typer.echo(f"Processing {len(requests)} pending requests")
        for request in requests:
            tasks = await uow.task_repository.list_by_request(request.id)
            for task in tasks:
                artifact_dir = (
                    container.settings.artifacts_root
                    / str(request.id)
                    / str(task.id)
                )
                ctx = ExecutionTaskContext(
                    request=request,
                    task=task,
                    artifact_dir=artifact_dir,
                )
                parsed = await _process_request(ctx)
                typer.echo(
                    f"Completed task {task.id} for provider {request.provider_id.value}"
                )
                typer.echo(json.dumps(parsed, indent=2))

                updated_task = task.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.SUCCEEDED,
                        "completed_at": utc_now(),
                        "metadata": dict(task.metadata) | {"artifact_dir": str(artifact_dir)},
                    }
                )
                await uow.task_repository.update(updated_task)

            updated_request = request.model_copy(
                update={
                    "lifecycle_state": LifecycleState.SUCCEEDED,
                    "completed_at": utc_now(),
                }
            )
            await uow.request_repository.update(updated_request)

        await uow.commit()

    typer.echo("Harvest complete")


@app.command()
def run(limit: int = typer.Option(25, help="Maximum number of requests to harvest")) -> None:
    """Process pending requests once using the configured runtimes."""

    asyncio.run(_harvest(limit))


if __name__ == "__main__":  # pragma: no cover
    app()
