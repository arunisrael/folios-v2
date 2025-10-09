"""Test Gemini batch submission and immediate job ID storage."""

from __future__ import annotations

import asyncio
from pathlib import Path

from dotenv import load_dotenv

# Load .env file before importing folios modules
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, LifecycleState, ProviderId
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.utils import utc_now


async def main() -> None:
    container = get_container()

    # Get one pending Gemini batch request
    async with container.unit_of_work_factory() as uow:
        requests = await uow.request_repository.list_pending(limit=100)
        gemini_requests = [r for r in requests if r.provider_id == ProviderId.GEMINI and r.mode == ExecutionMode.BATCH]

        if not gemini_requests:
            print("No pending Gemini batch requests found")
            return

        request = gemini_requests[0]
        print(f"\nProcessing Gemini request: {request.id}")
        print(f"Strategy: {request.strategy_id}")

        # Get the task
        tasks = await uow.task_repository.list_by_request(request.id)
        if not tasks:
            print("No tasks found for this request")
            return

        task = tasks[0]
        print(f"Task: {task.id}")

        # Create execution context
        artifact_dir = container.settings.artifacts_root / str(request.id) / str(task.id)
        ctx = ExecutionTaskContext(
            request=request,
            task=task,
            artifact_dir=artifact_dir,
        )

        # Get the Gemini plugin
        plugin = container.provider_registry.require(ProviderId.GEMINI, ExecutionMode.BATCH)

        # Serialize
        print("\n[1/3] Serializing...")
        serializer = plugin.serializer
        if serializer is None:
            print("ERROR: No serializer found")
            return

        payload = await serializer.serialize(ctx)
        print(f"✓ Payload created at: {payload.payload_path}")

        # Submit (this should now work with the timeout fix)
        print("\n[2/3] Submitting batch...")
        executor = plugin.batch_executor
        if executor is None:
            print("ERROR: No batch executor found")
            return

        try:
            submit_result = await executor.submit(ctx, payload)
            provider_job_id = submit_result.provider_job_id
            print("✓ Batch submitted successfully!")
            print(f"  Provider Job ID: {provider_job_id}")
            print(f"  Metadata: {submit_result.metadata}")

            # Store the job ID in the task
            print("\n[3/3] Storing job ID...")
            updated_task = task.model_copy(
                update={
                    "provider_job_id": provider_job_id,
                    "lifecycle_state": LifecycleState.RUNNING,
                    "started_at": utc_now(),
                    "metadata": dict(task.metadata) | {
                        "artifact_dir": str(artifact_dir),
                        "provider_metadata": submit_result.metadata,
                    },
                }
            )
            await uow.task_repository.update(updated_task)

            # Update request status
            updated_request = request.model_copy(
                update={
                    "lifecycle_state": LifecycleState.RUNNING,
                    "started_at": utc_now(),
                }
            )
            await uow.request_repository.update(updated_request)

            await uow.commit()
            print("✓ Job ID and status stored successfully!")

            print(f"\n{'='*60}")
            print("SUCCESS! Gemini batch submitted and tracked.")
            print(f"{'='*60}")
            print(f"Request ID: {request.id}")
            print(f"Task ID: {task.id}")
            print(f"Provider Job ID: {provider_job_id}")
            print(f"Artifact Directory: {artifact_dir}")
            print("\nThe batch job will process in the background.")
            print("Use scripts/check_gemini_batch.py to check status later.")

        except Exception as e:
            print("\n❌ ERROR during submission:")
            print(f"  {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return


if __name__ == "__main__":
    asyncio.run(main())
