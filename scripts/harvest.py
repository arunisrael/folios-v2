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
from folios_v2.providers.exceptions import ParseError
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.providers.unified_parser import UnifiedResultParser
from folios_v2.utils import utc_now

app = typer.Typer(help="Harvest pending requests by running their tasks once")


async def _process_request(ctx: ExecutionTaskContext) -> dict[str, object]:
    container = get_container()
    registry = container.provider_registry
    plugin = registry.require(ctx.request.provider_id, ctx.request.mode)

    # Use unified parser for all providers
    unified_parser = UnifiedResultParser(ctx.request.provider_id.value)

    if ctx.request.mode is ExecutionMode.BATCH:
        if plugin.serializer is None or plugin.batch_executor is None:
            raise typer.Exit(code=1)
        await plugin.serializer.serialize(ctx)
        outcome = await container.batch_runtime.run(plugin, ctx)
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


async def _harvest(limit: int) -> None:
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        requests = await uow.request_repository.list_pending(limit=limit)
        if not requests:
            typer.echo("No pending requests discovered")
            return

        typer.echo(f"Processing {len(requests)} pending requests")
        for request in requests:
            request_failed = False
            failure_error: str | None = None
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
                try:
                    parsed = await _process_request(ctx)
                except ParseError as exc:
                    typer.echo(
                        f"Skipping task {task.id}: {exc}",
                        err=True,
                    )
                    updated_task = task.model_copy(
                        update={
                            "lifecycle_state": LifecycleState.FAILED,
                            "completed_at": utc_now(),
                            "error": str(exc),
                            "metadata": dict(task.metadata)
                            | {"artifact_dir": str(artifact_dir)},
                        }
                    )
                    await uow.task_repository.update(updated_task)
                    request_failed = True
                    failure_error = str(exc)
                    break

                typer.echo(
                    f"Completed task {task.id} for provider {request.provider_id.value}"
                )
                typer.echo(json.dumps(parsed, indent=2))

                updated_task = task.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.SUCCEEDED,
                        "completed_at": utc_now(),
                        "metadata": dict(task.metadata)
                        | {"artifact_dir": str(artifact_dir)},
                    }
                )
                await uow.task_repository.update(updated_task)

            if request_failed:
                updated_request = request.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.FAILED,
                        "completed_at": utc_now(),
                        "error": failure_error,
                    }
                )
                await uow.request_repository.update(updated_request)
                continue

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
