"""Submit pending batch tasks to their providers."""

from __future__ import annotations

import asyncio
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
app = typer.Typer(help="Submit queued batch requests without polling")


async def _load_queue(limit: int, providers: list[str]) -> list[tuple[str, str]]:
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
          AND et.lifecycle_state IN ('pending', 'scheduled')
          AND r.lifecycle_state IN ('pending', 'scheduled')
          AND (
            json_extract(et.payload, '$.provider_job_id') IS NULL
            OR json_extract(et.payload, '$.provider_job_id') = ''
          )
        ORDER BY r.created_at
        LIMIT :limit
        """
    )

    async with container.unit_of_work_factory() as uow:
        cursor = await uow._session.execute(query, {"limit": limit})
        rows = cursor.fetchall()
    return [
        (row.task_id, row.request_id)
        for row in rows
        if not providers or row.provider_id in providers
    ]


async def _submit_task(task_id: str, request_id: str) -> tuple[bool, str]:
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        request = await uow.request_repository.get(request_id)
        task = await uow.task_repository.get(task_id)
        if request is None or task is None:
            return False, "request or task not found"

        registry = container.provider_registry
        plugin = registry.require(request.provider_id, ExecutionMode.BATCH)

        artifact_dir = (
            container.settings.artifacts_root
            / str(request.id)
            / str(task.id)
        )
        artifact_dir.mkdir(parents=True, exist_ok=True)
        ctx = ExecutionTaskContext(request=request, task=task, artifact_dir=artifact_dir)

        payload = await container.batch_runtime.serialize(plugin, ctx)
        submit_result = await container.batch_runtime.submit(plugin, ctx, payload)

        metadata = dict(task.metadata)
        metadata["artifact_dir"] = str(artifact_dir)
        metadata["provider_metadata"] = submit_result.metadata

        started_at = utc_now()
        updated_task = task.model_copy(
            update={
                "provider_job_id": submit_result.provider_job_id,
                "lifecycle_state": LifecycleState.RUNNING,
                "started_at": started_at,
                "metadata": metadata,
            }
        )
        await uow.task_repository.update(updated_task)

        request_started_at = request.started_at or started_at
        updated_request = request.model_copy(
            update={
                "lifecycle_state": LifecycleState.RUNNING,
                "started_at": request_started_at,
            }
        )
        await uow.request_repository.update(updated_request)
        await uow.commit()

        return True, submit_result.provider_job_id


@app.command()
def run(
    providers: str = typer.Option("openai,gemini", help="Comma separated provider list"),
    limit: int = typer.Option(20, help="Maximum number of tasks to submit"),
) -> None:
    """Submit queued batch requests and persist provider job IDs."""

    allowed_providers = {"openai", "gemini", "anthropic"}
    provider_list = [
        p.strip()
        for p in providers.split(",")
        if p.strip() and p.strip() in allowed_providers
    ]
    queue = asyncio.run(_load_queue(limit, provider_list))

    if not queue:
        console.print("[yellow]No pending batch tasks ready for submission.[/yellow]")
        return

    table = Table(title="Submitted Batch Jobs")
    table.add_column("Request ID", style="cyan", no_wrap=True)
    table.add_column("Task ID", style="magenta", no_wrap=True)
    table.add_column("Provider Job ID", style="green")
    table.add_column("Status", style="yellow")

    for task_id, request_id in queue:
        try:
            success, job_id = asyncio.run(_submit_task(task_id, request_id))
        except Exception as exc:  # pragma: no cover - defensive
            success = False
            job_id = str(exc)

        table.add_row(
            request_id,
            task_id,
            job_id if success else "-",
            "submitted" if success else "failed",
        )

    console.print(table)
    console.print(
        "\nNext step: run `make poll-batch-status` to monitor job progress."
    )


if __name__ == "__main__":  # pragma: no cover
    app()
