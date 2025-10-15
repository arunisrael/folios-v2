"""Poll batch jobs that are currently running."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, LifecycleState
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.utils import utc_now

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

console = Console()
app = typer.Typer(help="Poll running batch jobs and update their lifecycle state")


async def _load_running_tasks(limit: int, providers: list[str]) -> list[tuple[str, str]]:
    container = get_container()

    query = text(
        """
        SELECT
            et.id AS task_id,
            r.id AS request_id,
            r.provider_id,
            json_extract(et.payload, '$.provider_job_id') AS provider_job_id
        FROM execution_tasks et
        JOIN requests r ON et.request_id = r.id
        WHERE r.mode = 'batch'
          AND et.lifecycle_state = 'running'
          AND r.lifecycle_state = 'running'
          AND json_extract(et.payload, '$.provider_job_id') IS NOT NULL
        ORDER BY et.updated_at
        LIMIT :limit
        """
    )

    async with container.unit_of_work_factory() as uow:
        cursor = await uow._session.execute(query, {"limit": limit})
        rows = cursor.fetchall()
    return [
        (row.task_id, row.request_id)
        for row in rows
        if (not providers or row.provider_id in providers)
        and row.provider_job_id
    ]


async def _poll_task(task_id: str, request_id: str) -> tuple[str, str, str]:
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        request = await uow.request_repository.get(request_id)
        task = await uow.task_repository.get(task_id)
        if request is None or task is None:
            return request_id, task_id, "missing"

        registry = container.provider_registry
        plugin = registry.require(request.provider_id, ExecutionMode.BATCH)

        provider_job_id = task.provider_job_id
        if not provider_job_id:
            return request_id, task_id, "missing-job-id"

        artifact_dir = (
            container.settings.artifacts_root
            / str(request.id)
            / str(task.id)
        )
        ctx = ExecutionTaskContext(request=request, task=task, artifact_dir=artifact_dir)

        poll_result = await container.batch_runtime.poll_once(plugin, ctx, provider_job_id)

        metadata = dict(task.metadata)
        metadata["last_poll_status"] = poll_result.status
        metadata["last_polled_at"] = datetime.now(UTC).isoformat()
        if poll_result.metadata:
            metadata["last_poll_metadata"] = poll_result.metadata

        if poll_result.completed:
            next_state = LifecycleState.AWAITING_RESULTS
            message = "completed"
        elif poll_result.status in {"failed", "cancelled", "timeout"}:
            next_state = LifecycleState.FAILED
            message = poll_result.status
        else:
            next_state = LifecycleState.RUNNING
            message = poll_result.status

        updated_task = task.model_copy(
            update={
                "lifecycle_state": next_state,
                "updated_at": utc_now(),
                "metadata": metadata,
            }
        )
        await uow.task_repository.update(updated_task)

        if next_state is LifecycleState.AWAITING_RESULTS:
            updated_request = request.model_copy(
                update={
                    "lifecycle_state": LifecycleState.AWAITING_RESULTS,
                    "updated_at": utc_now(),
                }
            )
        elif next_state is LifecycleState.FAILED:
            updated_request = request.model_copy(
                update={
                    "lifecycle_state": LifecycleState.FAILED,
                    "completed_at": utc_now(),
                    "updated_at": utc_now(),
                }
            )
        else:
            updated_request = request.model_copy(
                update={
                    "updated_at": utc_now(),
                }
            )

        await uow.request_repository.update(updated_request)
        await uow.commit()
        return request_id, task_id, message


@app.command()
def run(
    providers: str = typer.Option("openai,gemini", help="Comma separated provider list"),
    limit: int = typer.Option(25, help="Maximum number of running tasks to poll"),
) -> None:
    """Poll running batch jobs and update lifecycle state."""

    allowed_providers = {"openai", "gemini", "anthropic"}
    provider_list = [
        p.strip()
        for p in providers.split(",")
        if p.strip() and p.strip() in allowed_providers
    ]
    queue = asyncio.run(_load_running_tasks(limit, provider_list))

    if not queue:
        console.print("[yellow]No running batch tasks found.[/yellow]")
        return

    table = Table(title="Batch Poll Results")
    table.add_column("Request ID", style="cyan", no_wrap=True)
    table.add_column("Task ID", style="magenta", no_wrap=True)
    table.add_column("Status", style="green")

    for task_id, request_id in queue:
        try:
            result = asyncio.run(_poll_task(task_id, request_id))
        except Exception as exc:  # pragma: no cover - defensive
            result = (request_id, task_id, f"error: {exc}")
        table.add_row(*result)

    console.print(table)
    console.print(
        "\nCompleted jobs move to AWAITING_RESULTS. Run `make harvest-batch-results` next."
    )


if __name__ == "__main__":  # pragma: no cover
    app()
