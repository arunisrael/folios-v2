"""Monitor and harvest Gemini batches in a loop until all complete."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

# Load .env file before importing folios modules
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from sqlalchemy import text

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, LifecycleState, ProviderId
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.providers.unified_parser import UnifiedResultParser
from folios_v2.utils import utc_now


async def check_and_harvest() -> tuple[int, int, int]:
    """Check and harvest completed batches. Returns (completed, running, failed)."""
    container = get_container()

    async with container.unit_of_work_factory() as uow:
        # Query running Gemini batch tasks
        query = """
            SELECT
                et.id as task_id,
                json_extract(et.payload, '$.provider_job_id') as provider_job_id,
                r.id as request_id
            FROM execution_tasks et
            JOIN requests r ON et.request_id = r.id
            WHERE r.mode = 'batch'
              AND r.provider_id = 'gemini'
              AND et.lifecycle_state IN ('running', 'pending')
            ORDER BY et.created_at ASC
        """

        cursor = await uow._session.execute(text(query))
        rows = cursor.fetchall()

        if not rows:
            return (0, 0, 0)

        # Get the Gemini plugin
        plugin = container.provider_registry.require(ProviderId.GEMINI, ExecutionMode.BATCH)
        executor = plugin.batch_executor
        if executor is None:
            return (0, 0, 0)

        unified_parser = UnifiedResultParser(ProviderId.GEMINI.value)

        completed_count = 0
        still_running_count = 0
        failed_count = 0

        for row in rows:
            task_id = row[0]
            provider_job_id = row[1]
            request_id = row[2]

            if not provider_job_id:
                continue

            # Get full request and task objects
            request = await uow.request_repository.get(request_id)
            task = await uow.task_repository.get(task_id)

            if not request or not task:
                continue

            # Create execution context
            artifact_dir = container.settings.artifacts_root / str(request.id) / str(task.id)
            ctx = ExecutionTaskContext(
                request=request,
                task=task,
                artifact_dir=artifact_dir,
            )

            try:
                # Poll the batch job
                poll_result = await executor.poll(ctx, provider_job_id)

                if poll_result.completed:
                    print(f"  ✓ Task {task_id[:24]} completed! Downloading...")

                    # Download results
                    download_result = await executor.download(ctx, provider_job_id)

                    # Parse results
                    parsed = await unified_parser.parse(ctx)
                    parsed["provider_job_id"] = provider_job_id

                    # Save parsed results
                    parsed_path = artifact_dir / "parsed.json"
                    parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

                    # Update task status
                    updated_task = task.model_copy(
                        update={
                            "lifecycle_state": LifecycleState.SUCCEEDED,
                            "completed_at": utc_now(),
                            "metadata": dict(task.metadata) | {
                                "artifact_dir": str(artifact_dir),
                                "parsed_path": str(parsed_path),
                            },
                        }
                    )
                    await uow.task_repository.update(updated_task)

                    # Update request status
                    updated_request = request.model_copy(
                        update={
                            "lifecycle_state": LifecycleState.SUCCEEDED,
                            "completed_at": utc_now(),
                        }
                    )
                    await uow.request_repository.update(updated_request)

                    await uow.commit()

                    completed_count += 1

                else:
                    still_running_count += 1

            except Exception as e:
                print(f"  ✗ Task {task_id[:24]} failed: {e}")
                failed_count += 1

                # Update task with error
                updated_task = task.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.FAILED,
                        "completed_at": utc_now(),
                        "error": str(e),
                    }
                )
                await uow.task_repository.update(updated_task)

                updated_request = request.model_copy(
                    update={
                        "lifecycle_state": LifecycleState.FAILED,
                        "completed_at": utc_now(),
                        "error": str(e),
                    }
                )
                await uow.request_repository.update(updated_request)

                await uow.commit()

        return (completed_count, still_running_count, failed_count)


async def main() -> None:
    """Monitor and harvest until all batches complete."""
    print("\n" + "="*60)
    print("MONITORING GEMINI BATCHES")
    print("="*60)
    print("Will check every 30 seconds until all batches complete...\n")

    total_completed = 0
    total_failed = 0
    iteration = 0

    while True:
        iteration += 1
        print(f"[Check #{iteration}]")

        completed, running, failed = await check_and_harvest()

        total_completed += completed
        total_failed += failed

        print(f"  Newly completed: {completed}")
        print(f"  Still running: {running}")
        print(f"  Newly failed: {failed}")
        print(f"  Total completed so far: {total_completed}")
        print(f"  Total failed so far: {total_failed}")

        if running == 0:
            print("\n" + "="*60)
            print("ALL BATCHES COMPLETED!")
            print("="*60)
            print(f"Total completed: {total_completed}")
            print(f"Total failed: {total_failed}")
            print("="*60 + "\n")
            break

        print("  Waiting 30 seconds...\n")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
