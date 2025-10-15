"""Harvest research requests in staged batch/CLI workflows."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import NamedTuple

import typer
from dotenv import load_dotenv
from sqlalchemy import text

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, LifecycleState
from folios_v2.providers.exceptions import ParseError
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.providers.unified_parser import UnifiedResultParser
from folios_v2.utils import utc_now

# Load .env file before importing folios modules
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

app = typer.Typer(help="Harvest completed requests and update lifecycle state")


class HarvestSummary(NamedTuple):
    succeeded: int
    failed: int
    skipped: int


async def _list_batch_requests_to_harvest(limit: int) -> Sequence[str]:
    """Return request IDs that are ready for batch download."""

    container = get_container()
    async with container.unit_of_work_factory() as uow:
        query = text(
            """
            SELECT id
            FROM requests
            WHERE mode = 'batch'
              AND lifecycle_state = :awaiting
            ORDER BY created_at
            LIMIT :limit
            """
        )
        cursor = await uow._session.execute(
            query,
            {
                "awaiting": LifecycleState.AWAITING_RESULTS.value,
                "limit": limit,
            },
        )
        return tuple(row[0] for row in cursor.fetchall())


async def _list_cli_requests_to_finalize(limit: int) -> Sequence[str]:
    """Return CLI request IDs that are still pending and need parsing."""

    container = get_container()
    async with container.unit_of_work_factory() as uow:
        pending = await uow.request_repository.list_pending(limit=limit)
        return tuple(
            str(request.id)
            for request in pending
            if request.mode is ExecutionMode.CLI
        )


async def _parse_cli_task(ctx: ExecutionTaskContext) -> dict[str, object]:
    unified_parser = UnifiedResultParser(ctx.request.provider_id.value)
    parsed = await unified_parser.parse(ctx)

    # Optional CLI exit code stored in response.json
    response_path = ctx.artifact_dir / "response.json"
    if response_path.exists():
        try:
            response_data = json.loads(response_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
        else:
            if "exit_code" in response_data:
                parsed["cli_exit_code"] = response_data["exit_code"]
    return parsed


async def _handle_cli_request(request_id: str) -> HarvestSummary:
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        request = await uow.request_repository.get(request_id)
        if request is None:
            return HarvestSummary(0, 0, 1)
        tasks = await uow.task_repository.list_by_request(request.id)

        succeeded, failed = 0, 0
        for task in tasks:
            artifact_dir = (
                container.settings.artifacts_root
                / str(request.id)
                / str(task.id)
            )
            ctx = ExecutionTaskContext(request=request, task=task, artifact_dir=artifact_dir)
            try:
                parsed = await _parse_cli_task(ctx)
            except ParseError as exc:
                updated_task = task.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.FAILED,
                        "completed_at": utc_now(),
                        "error": str(exc),
                        "metadata": dict(task.metadata),
                    }
                )
                await uow.task_repository.update(updated_task)
                typer.echo(f"[CLI] Failed to parse task {task.id}: {exc}", err=True)
                failed += 1
                continue

            parsed_path = artifact_dir / "parsed.json"
            parsed_path.parent.mkdir(parents=True, exist_ok=True)
            parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

            metadata = dict(task.metadata)
            metadata["artifact_dir"] = str(artifact_dir)
            metadata["parsed_path"] = str(parsed_path)

            updated_task = task.model_copy(
                update={
                    "lifecycle_state": LifecycleState.SUCCEEDED,
                    "completed_at": utc_now(),
                    "metadata": metadata,
                    "cli_exit_code": parsed.get("cli_exit_code"),
                }
            )
            await uow.task_repository.update(updated_task)
            succeeded += 1

        if succeeded and not failed:
            updated_request = request.model_copy(
                update={
                    "lifecycle_state": LifecycleState.SUCCEEDED,
                    "completed_at": utc_now(),
                }
            )
        elif failed and not succeeded:
            updated_request = request.model_copy(
                update={
                    "lifecycle_state": LifecycleState.FAILED,
                    "completed_at": utc_now(),
                }
            )
        else:
            # Mixed results - keep request pending for manual inspection
            updated_request = request

        await uow.request_repository.update(updated_request)
        await uow.commit()
        return HarvestSummary(succeeded, failed, 0)


async def _handle_batch_request(request_id: str) -> HarvestSummary:
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        request = await uow.request_repository.get(request_id)
        if request is None:
            typer.echo(f"[BATCH] Request {request_id} not found", err=True)
            return HarvestSummary(0, 0, 1)
        tasks = await uow.task_repository.list_by_request(request.id)

        registry = container.provider_registry
        plugin = registry.require(request.provider_id, ExecutionMode.BATCH)
        unified_parser = UnifiedResultParser(request.provider_id.value)

        succeeded, failed = 0, 0

        for task in tasks:
            provider_job_id = task.provider_job_id
            if not provider_job_id:
                typer.echo(
                    f"[BATCH] Task {task.id} missing provider_job_id - skipping",
                    err=True,
                )
                failed += 1
                continue

            artifact_dir = (
                container.settings.artifacts_root
                / str(request.id)
                / str(task.id)
            )
            ctx = ExecutionTaskContext(request=request, task=task, artifact_dir=artifact_dir)

            try:
                download_result = await container.batch_runtime.download(
                    plugin,
                    ctx,
                    provider_job_id,
                )
            except Exception as exc:  # pragma: no cover - defensive
                typer.echo(
                    f"[BATCH] Download failed for {task.id}: {exc}",
                    err=True,
                )
                updated_task = task.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.FAILED,
                        "completed_at": utc_now(),
                        "error": str(exc),
                    }
                )
                await uow.task_repository.update(updated_task)
                failed += 1
                continue

            try:
                parsed = await unified_parser.parse(ctx)
            except ParseError as exc:
                typer.echo(f"[BATCH] Parse failed for {task.id}: {exc}", err=True)
                updated_task = task.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.FAILED,
                        "completed_at": utc_now(),
                        "error": str(exc),
                    }
                )
                await uow.task_repository.update(updated_task)
                failed += 1
                continue

            parsed_path = artifact_dir / "parsed.json"
            parsed_path.parent.mkdir(parents=True, exist_ok=True)
            parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

            metadata = dict(task.metadata)
            metadata["artifact_dir"] = str(artifact_dir)
            metadata["parsed_path"] = str(parsed_path)
            metadata["download_metadata"] = download_result.metadata

            updated_task = task.model_copy(
                update={
                    "lifecycle_state": LifecycleState.SUCCEEDED,
                    "completed_at": utc_now(),
                    "metadata": metadata,
                }
            )
            await uow.task_repository.update(updated_task)
            succeeded += 1

        if succeeded and not failed:
            updated_request = request.model_copy(
                update={
                    "lifecycle_state": LifecycleState.SUCCEEDED,
                    "completed_at": utc_now(),
                }
            )
        elif failed and not succeeded:
            updated_request = request.model_copy(
                update={
                    "lifecycle_state": LifecycleState.FAILED,
                    "completed_at": utc_now(),
                }
            )
        else:
            updated_request = request

        await uow.request_repository.update(updated_request)
        await uow.commit()
        return HarvestSummary(succeeded, failed, 0)


def _aggregate(summaries: Iterable[HarvestSummary]) -> HarvestSummary:
    total_succeeded = total_failed = total_skipped = 0
    for summary in summaries:
        total_succeeded += summary.succeeded
        total_failed += summary.failed
        total_skipped += summary.skipped
    return HarvestSummary(total_succeeded, total_failed, total_skipped)


async def _harvest(limit: int) -> None:
    cli_requests = await _list_cli_requests_to_finalize(limit)
    batch_requests = await _list_batch_requests_to_harvest(limit)

    typer.echo(
        f"CLI requests to finalize: {len(cli_requests)} • "
        f"Batch requests to harvest: {len(batch_requests)}"
    )

    summaries: list[HarvestSummary] = []

    for request_id in cli_requests:
        typer.echo(f"[CLI] Harvesting request {request_id}")
        summaries.append(await _handle_cli_request(request_id))

    for request_id in batch_requests:
        typer.echo(f"[BATCH] Harvesting request {request_id}")
        summaries.append(await _handle_batch_request(request_id))

    total = _aggregate(summaries)
    typer.echo("\nHarvest summary")
    typer.echo("===============")
    typer.echo(f"Succeeded: {total.succeeded}")
    typer.echo(f"Failed:    {total.failed}")
    typer.echo(f"Skipped:   {total.skipped}")


@app.command()
def run(
    limit: int = typer.Option(25, help="Maximum number of requests per mode to process"),
) -> None:
    """Finalize CLI requests and download completed batch jobs."""

    asyncio.run(_harvest(limit))


if __name__ == "__main__":  # pragma: no cover
    app()
