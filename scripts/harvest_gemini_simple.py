"""Harvest completed Gemini batch jobs and parse results (simple version)."""

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


async def main() -> None:
    container = get_container()

    print("\nChecking for completed Gemini batch jobs...\n")

    async with container.unit_of_work_factory() as uow:
        # Query running Gemini batch tasks
        query = """
            SELECT
                et.id as task_id,
                et.lifecycle_state,
                json_extract(et.payload, '$.provider_job_id') as provider_job_id,
                r.id as request_id,
                r.provider_id,
                r.strategy_id
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
            print("No running Gemini batch jobs found")
            return

        print(f"Found {len(rows)} running Gemini batch job(s)\n")

        # Get the Gemini plugin
        plugin = container.provider_registry.require(ProviderId.GEMINI, ExecutionMode.BATCH)
        executor = plugin.batch_executor
        if executor is None:
            print("ERROR: No Gemini batch executor found")
            return

        unified_parser = UnifiedResultParser(ProviderId.GEMINI.value)

        completed_count = 0
        still_running_count = 0
        failed_count = 0

        for row in rows:
            task_id = row[0]
            provider_job_id = row[2]
            request_id = row[3]

            if not provider_job_id:
                print(f"  • Task {task_id[:24]}: No job ID (skipping)")
                continue

            print(f"  • Task {task_id[:24]}")
            print(f"    Job ID: {provider_job_id}")

            # Get full request and task objects
            request = await uow.request_repository.get(request_id)
            task = await uow.task_repository.get(task_id)

            if not request or not task:
                print("    ERROR: Request or task not found")
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

                print(f"    Status: {poll_result.status}")
                if poll_result.metadata:
                    metadata = poll_result.metadata
                    if isinstance(metadata, dict) and "counts" in metadata:
                        counts = metadata["counts"]
                        print(f"    Progress: {counts.get('completed', 0)}/{counts.get('total', 0)}")

                if poll_result.completed:
                    print("    ✓ Job completed! Downloading results...")

                    # Download results
                    download_result = await executor.download(ctx, provider_job_id)
                    print(f"    ✓ Downloaded to: {download_result.artifact_path}")

                    # Parse results
                    parsed = await unified_parser.parse(ctx)
                    parsed["provider_job_id"] = provider_job_id

                    # Save parsed results
                    parsed_path = artifact_dir / "parsed.json"
                    parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
                    print(f"    ✓ Parsed results saved to: {parsed_path}")

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

                    print("    ✓ Task marked as SUCCEEDED\n")
                    completed_count += 1

                else:
                    print("    Still processing...\n")
                    still_running_count += 1

            except Exception as e:
                print(f"    ERROR: {type(e).__name__}: {e}\n")
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

        print(f"{'='*60}")
        print("Harvest Summary:")
        print(f"  Completed: {completed_count}")
        print(f"  Still Running: {still_running_count}")
        print(f"  Failed: {failed_count}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
