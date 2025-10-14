"""Run 10 selected strategies through Gemini CLI mode serially."""

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
from folios_v2.domain import ExecutionMode, ProviderId, RequestPriority, RequestType
from folios_v2.domain.types import StrategyId
from folios_v2.utils import utc_now

# Selected strategy IDs
STRATEGIES = [
    ("9a089867-8137-45ed-8a7f-f735f83e0190", "Warren Buffett Quality Growth Strategy"),
    ("e0813c83-0cd7-4061-8c4f-f0aaed3cb1f0", "Mason Hawkins Strategy"),
    ("4cb2546a-5aa2-4dfb-8d71-217842c6286a", "High-Dividend Investing"),
    ("0a245bcc-9b76-4139-b2c5-9886c1bcb955", "David Shaw Strategy"),
    ("e04d2c5d-0811-4441-bd0c-2807446dad1d", "Bill Ackman Strategy"),
    ("64e06a91-5413-4207-bc24-1108b69660a3", "Peter Lynch Small Cap Strategy"),
    ("24fecb8f-cb85-4194-8bfd-e5b087f08f45", "Joel Greenblatt Strategy"),
    ("1b34a9b6-4cb9-4e6b-9a31-fd666f63dd6c", "Thomas Rowe Price Jr Strategy"),
    ("3cf40398-6bb5-48c4-9b24-44d0a63af703", "Event-Driven Activism"),
    ("6b291794-02b8-471f-b02c-24d78802164f", "Benjamin Graham Cigar Butt Strategy"),
]


async def run_strategy_cli(strategy_id_str: str, strategy_name: str) -> tuple[str, str, str | None]:
    """Run a single strategy via Gemini CLI and return result."""
    container = get_container()

    try:
        async with container.unit_of_work_factory() as uow:
            # Get strategy
            sid = StrategyId(UUID(strategy_id_str))
            strategy = await uow.strategy_repository.get(sid)
            if strategy is None:
                return (strategy_name, "ERROR", "Strategy not found")

            print(f"\n{'='*60}")
            print(f"Strategy: {strategy.name}")
            print(f"ID: {strategy_id_str}")
            print(f"{'='*60}")

            # Create and execute request via CLI mode
            print("[1/2] Creating CLI request...")
            request, task = await container.request_orchestrator.enqueue_request(
                strategy,
                provider_id=ProviderId.GEMINI,
                request_type=RequestType.RESEARCH,
                mode=ExecutionMode.CLI,
                priority=RequestPriority.NORMAL,
                scheduled_for=utc_now(),
                metadata={"triggered_by": "run_strategies_cli_script"},
            )
            await uow.commit()
            print(f"✓ Request: {request.id}, Task: {task.id}")

        # Execute the task
        print("[2/2] Executing via CLI...")
        result = await container.task_executor.execute_task(task.id)

        if result.success:
            print(f"✓ SUCCESS! Result saved to: {result.artifact_path}")
            return (strategy_name, "SUCCESS", str(result.artifact_path))
        else:
            print(f"✗ FAILED: {result.error}")
            return (strategy_name, "FAILED", str(result.error))

    except Exception as e:
        print(f"✗ ERROR: {type(e).__name__}: {e}")
        return (strategy_name, "ERROR", str(e))


async def main() -> None:
    """Run all strategies serially via CLI."""
    print("\n" + "="*60)
    print("GEMINI CLI EXECUTION WORKFLOW")
    print("="*60)
    print(f"Running {len(STRATEGIES)} strategies via Gemini CLI")
    print("="*60 + "\n")

    results = []
    for i, (strategy_id, strategy_name) in enumerate(STRATEGIES, 1):
        print(f"\n### Processing {i}/{len(STRATEGIES)} ###")
        result = await run_strategy_cli(strategy_id, strategy_name)
        results.append(result)

        # Small delay between executions
        if i < len(STRATEGIES):
            await asyncio.sleep(1)

    # Print summary
    print("\n" + "="*60)
    print("EXECUTION SUMMARY")
    print("="*60)

    success_count = sum(1 for _, status, _ in results if status == "SUCCESS")
    failed_count = sum(1 for _, status, _ in results if status == "FAILED")
    error_count = sum(1 for _, status, _ in results if status == "ERROR")

    print(f"\nTotal: {len(results)}")
    print(f"Success: {success_count}")
    print(f"Failed: {failed_count}")
    print(f"Errors: {error_count}\n")

    for name, status, detail in results:
        status_icon = "✓" if status == "SUCCESS" else "✗"
        print(f"{status_icon} {name}: {status}")
        if detail and status != "SUCCESS":
            print(f"   {detail}")

    print("\n" + "="*60)


if __name__ == "__main__":
    asyncio.run(main())
