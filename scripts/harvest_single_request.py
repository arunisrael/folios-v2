"""Harvest a single request by ID."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import UUID

import typer
from dotenv import load_dotenv

# Load .env file before importing folios modules
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, LifecycleState
from folios_v2.domain.types import RequestId
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.providers.unified_parser import UnifiedResultParser
from folios_v2.utils import utc_now

app = typer.Typer(help="Harvest a single request by ID")


async def _process_request(ctx: ExecutionTaskContext) -> dict[str, object]:
    container = get_container()
    registry = container.provider_registry
    plugin = registry.require(ctx.request.provider_id, ctx.request.mode)

    # Use unified parser for all providers
    unified_parser = UnifiedResultParser(ctx.request.provider_id.value)

    if ctx.request.mode is ExecutionMode.BATCH:
        if plugin.serializer is None or plugin.batch_executor is None:
            raise typer.Exit(code=1)

        typer.echo("Serializing request...")
        await plugin.serializer.serialize(ctx)

        typer.echo("Running batch execution (this may take several minutes)...")
        outcome = await container.batch_runtime.run(plugin, ctx)

        typer.echo("Parsing results...")
        parsed = await unified_parser.parse(ctx)
        parsed["provider_job_id"] = outcome.submit_result.provider_job_id
    else:
        # For CLI mode, results already exist - just parse them
        parsed = await unified_parser.parse(ctx)
        # Check if exit code is stored in response.json
        response_path = ctx.artifact_dir / "response.json"
        if response_path.exists():
            try:
                response_data = json.loads(response_path.read_text(encoding="utf-8"))
                if "exit_code" in response_data:
                    parsed["cli_exit_code"] = response_data["exit_code"]
            except (json.JSONDecodeError, OSError):
                pass

    parsed_path = ctx.artifact_dir / "parsed.json"
    parsed_path.parent.mkdir(parents=True, exist_ok=True)
    parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    return parsed


async def _harvest_single(request_id: str, verbose: bool) -> None:
    container = get_container()
    request_uuid = RequestId(UUID(request_id))

    async with container.unit_of_work_factory() as uow:
        request = await uow.request_repository.get(request_uuid)
        if request is None:
            typer.echo(f"Request {request_id} not found", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"Found request: {request.id}")
        typer.echo(f"  Provider: {request.provider_id.value}")
        typer.echo(f"  Mode: {request.mode.value}")
        typer.echo(f"  State: {request.lifecycle_state.value}")
        typer.echo(f"  Strategy: {request.strategy_id}")

        tasks = await uow.task_repository.list_by_request(request.id)
        if not tasks:
            typer.echo("No tasks found for this request", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"\nProcessing {len(tasks)} task(s)...")

        for task in tasks:
            typer.echo(f"\nTask: {task.id}")
            typer.echo(f"  State: {task.lifecycle_state.value}")

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

            try:
                parsed = await _process_request(ctx)
                typer.echo(f"✓ Completed task {task.id}")

                if verbose:
                    typer.echo("\nParsed result:")
                    typer.echo(json.dumps(parsed, indent=2))

                updated_task = task.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.SUCCEEDED,
                        "completed_at": utc_now(),
                        "metadata": dict(task.metadata) | {"artifact_dir": str(artifact_dir)},
                        "provider_job_id": parsed.get("provider_job_id"),
                    }
                )
                await uow.task_repository.update(updated_task)

            except Exception as e:
                typer.echo(f"✗ Failed to process task {task.id}: {e}", err=True)

                # Update task with error
                updated_task = task.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.FAILED,
                        "completed_at": utc_now(),
                        "error": str(e),
                    }
                )
                await uow.task_repository.update(updated_task)
                await uow.commit()
                raise typer.Exit(code=1)

        # Mark request as succeeded
        updated_request = request.model_copy(
            update={
                "lifecycle_state": LifecycleState.SUCCEEDED,
                "completed_at": utc_now(),
            }
        )
        await uow.request_repository.update(updated_request)
        await uow.commit()

    typer.echo(f"\n✓ Request {request_id} successfully harvested")


@app.command()
def run(
    request_id: str = typer.Argument(..., help="Request ID to harvest"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
) -> None:
    """Harvest a single request by ID."""
    asyncio.run(_harvest_single(request_id, verbose))


if __name__ == "__main__":
    app()
