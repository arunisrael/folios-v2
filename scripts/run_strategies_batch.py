"""Run 10 selected strategies through full Gemini batch workflow."""

from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

# Load .env file before importing folios modules
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, LifecycleState, ProviderId, RequestPriority, RequestType
from folios_v2.domain.types import StrategyId
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.utils import utc_now

# Selected strategy IDs
STRATEGY_IDS = [
    "7f177d0f-f16d-40b9-b582-8d81559c4bb0",  # Pat Dorsey Strategy
    "345f9b6f-50f5-4d63-9d70-34a824e55eff",  # Michael Price Strategy
    "d6cd2e7e-044d-4d2a-8459-ca3e538d8a51",  # Jim Simons Strategy
    "9119eab4-3c5d-4b5d-bd0f-6e08aa302671",  # Nicolas Darvas Strategy
    "1b34a9b6-4cb9-4e6b-9a31-fd666f63dd6c",  # Thomas Rowe Price Jr Strategy
    "19ba440a-da27-4819-b691-d3d8cc76ff19",  # Carl Icahn Strategy
    "3d41ab75-db89-40b8-9d55-1ebd094c440d",  # William O'Neil Strategy
    "d75d1377-1721-4f1b-852c-f54bb495847a",  # Benjamin Graham Strategy
    "740c31df-eb4e-4cba-ac4a-f6560c49ee35",  # Scuttlebutt Qualitative Research
    "5d8109fa-c277-4d5d-8670-523391e824ba",  # Steven Cohen Strategy
]


async def create_and_submit_request(strategy_id_str: str) -> tuple[str, str, str | None]:
    """Create request and submit to Gemini batch."""
    container = get_container()

    async with container.unit_of_work_factory() as uow:
        # Get strategy
        sid = StrategyId(UUID(strategy_id_str))
        strategy = await uow.strategy_repository.get(sid)
        if strategy is None:
            return (strategy_id_str, "ERROR", "Strategy not found")

        print(f"\n{'='*60}")
        print(f"Strategy: {strategy.name}")
        print(f"ID: {strategy_id_str}")
        print(f"{'='*60}")

        # Create request
        print("[1/4] Creating request...")
        request, task = await container.request_orchestrator.enqueue_request(
            strategy,
            provider_id=ProviderId.GEMINI,
            request_type=RequestType.RESEARCH,
            mode=ExecutionMode.BATCH,
            priority=RequestPriority.NORMAL,
            scheduled_for=utc_now(),
            metadata={"triggered_by": "run_strategies_batch_script"},
        )
        await uow.commit()
        print(f"✓ Request created: {request.id}")
        print(f"✓ Task created: {task.id}")

    # Now submit the batch
    async with container.unit_of_work_factory() as uow:
        # Get the plugin
        plugin = container.provider_registry.require(ProviderId.GEMINI, ExecutionMode.BATCH)

        # Refresh request and task
        request = await uow.request_repository.get(request.id)
        task = await uow.task_repository.get(task.id)

        # Create execution context
        artifact_dir = container.settings.artifacts_root / str(request.id) / str(task.id)
        ctx = ExecutionTaskContext(
            request=request,
            task=task,
            artifact_dir=artifact_dir,
        )

        # Serialize
        print("[2/4] Serializing...")
        serializer = plugin.serializer
        if serializer is None:
            return (strategy_id_str, "ERROR", "No serializer")

        payload = await serializer.serialize(ctx)
        print(f"✓ Payload: {payload.payload_path}")

        # Submit
        print("[3/4] Submitting to Gemini...")
        executor = plugin.batch_executor
        if executor is None:
            return (strategy_id_str, "ERROR", "No executor")

        try:
            submit_result = await executor.submit(ctx, payload)
            provider_job_id = submit_result.provider_job_id
            print(f"✓ Submitted! Job ID: {provider_job_id}")

            # Store the job ID
            print("[4/4] Updating database...")
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

            updated_request = request.model_copy(
                update={
                    "lifecycle_state": LifecycleState.RUNNING,
                    "started_at": utc_now(),
                }
            )
            await uow.request_repository.update(updated_request)

            await uow.commit()
            print("✓ Database updated!")

            return (strategy.name, "SUCCESS", provider_job_id)

        except Exception as e:
            print(f"❌ ERROR: {e}")
            return (strategy.name, "ERROR", str(e))


async def main() -> None:
    """Run all strategies serially."""
    print("\n" + "="*60)
    print("BATCH SUBMISSION WORKFLOW")
    print("="*60)
    print(f"Submitting {len(STRATEGY_IDS)} strategies to Gemini batch")
    print("="*60 + "\n")

    results = []
    for i, strategy_id in enumerate(STRATEGY_IDS, 1):
        print(f"\n### Processing {i}/{len(STRATEGY_IDS)} ###")
        result = await create_and_submit_request(strategy_id)
        results.append(result)

        # Small delay between submissions
        if i < len(STRATEGY_IDS):
            await asyncio.sleep(2)

    # Print summary
    print("\n" + "="*60)
    print("SUBMISSION SUMMARY")
    print("="*60)

    success_count = sum(1 for _, status, _ in results if status == "SUCCESS")
    error_count = len(results) - success_count

    print(f"\nTotal: {len(results)}")
    print(f"Success: {success_count}")
    print(f"Errors: {error_count}\n")

    for name, status, detail in results:
        if status == "SUCCESS":
            print(f"✓ {name}: {detail}")
        else:
            print(f"✗ {name}: {detail}")

    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(main())
