"""Run 10 selected strategies serially via Gemini CLI."""

from __future__ import annotations

import asyncio
import json
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
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.providers.unified_parser import UnifiedResultParser
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


async def run_strategy_cli(strategy_id_str: str, strategy_name: str) -> tuple[str, str, str | None, int]:
    """Run a single strategy via Gemini CLI and return (name, status, detail, rec_count)."""
    container = get_container()
    provider_enum = ProviderId.GEMINI

    try:
        async with container.unit_of_work_factory() as uow:
            # Get strategy
            strategy_uuid = StrategyId(UUID(strategy_id_str))
            strategy = await uow.strategy_repository.get(strategy_uuid)
            if strategy is None:
                return (strategy_name, "ERROR", "Strategy not found", 0)

            print(f"\n{'='*60}")
            print(f"Strategy: {strategy.name}")
            print(f"ID: {strategy_id_str}")
            print(f"{'='*60}")

            # Check if provider supports CLI mode
            try:
                plugin = container.provider_registry.require(provider_enum, ExecutionMode.CLI)
            except Exception as e:
                return (strategy_name, "ERROR", f"Provider does not support CLI: {e}", 0)

            if not plugin.supports_cli:
                return (strategy_name, "ERROR", "Provider does not support CLI mode", 0)

            # Create request
            print("[1/4] Creating CLI request...")
            request, task = await container.request_orchestrator.enqueue_request(
                strategy,
                provider_id=provider_enum,
                request_type=RequestType.RESEARCH,
                mode=ExecutionMode.CLI,
                priority=RequestPriority.NORMAL,
                scheduled_for=utc_now(),
                metadata={"triggered_by": "run_10_strategies_cli_script"},
            )

            await uow.commit()
            print(f"✓ Request: {request.id}")
            print(f"✓ Task: {task.id}")

        # Execute CLI immediately
        artifact_dir = container.settings.artifacts_root / str(request.id) / str(task.id)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        ctx = ExecutionTaskContext(
            request=request,
            task=task,
            artifact_dir=artifact_dir,
        )

        print("[2/4] Executing via Gemini CLI...")
        result = await container.cli_runtime.run(plugin, ctx)

        print(f"✓ CLI completed (exit code: {result.result.exit_code})")
        print(f"  Artifact dir: {artifact_dir}")

        # Parse results
        print("[3/4] Parsing results...")
        unified_parser = UnifiedResultParser("gemini")
        parsed = await unified_parser.parse(ctx)
        parsed["cli_exit_code"] = result.result.exit_code

        # Save parsed results
        parsed_path = artifact_dir / "parsed.json"
        parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
        print(f"✓ Parsed results: {parsed_path}")

        recommendations = parsed.get("recommendations", [])
        rec_count = len(recommendations)
        print(f"[4/4] Found {rec_count} recommendations")

        if result.result.exit_code == 0:
            return (strategy_name, "SUCCESS", str(request.id), rec_count)
        else:
            return (strategy_name, "COMPLETED_WITH_ERRORS", str(request.id), rec_count)

    except Exception as e:
        print(f"✗ ERROR: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return (strategy_name, "ERROR", str(e), 0)


async def main() -> None:
    """Run all strategies serially via Gemini CLI."""
    print("\n" + "="*60)
    print("GEMINI CLI EXECUTION - 10 STRATEGIES")
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
            print("\nWaiting 2 seconds before next strategy...")
            await asyncio.sleep(2)

    # Print summary
    print("\n" + "="*60)
    print("EXECUTION SUMMARY")
    print("="*60)

    success_count = sum(1 for _, status, _, _ in results if status == "SUCCESS")
    completed_with_errors = sum(1 for _, status, _, _ in results if status == "COMPLETED_WITH_ERRORS")
    error_count = sum(1 for _, status, _, _ in results if status == "ERROR")
    total_recs = sum(count for _, _, _, count in results)

    print(f"\nTotal Strategies: {len(results)}")
    print(f"Success: {success_count}")
    print(f"Completed with errors: {completed_with_errors}")
    print(f"Errors: {error_count}")
    print(f"Total Recommendations: {total_recs}\n")

    for name, status, detail, rec_count in results:
        status_icon = "✓" if status == "SUCCESS" else "!" if status == "COMPLETED_WITH_ERRORS" else "✗"
        if status == "SUCCESS" or status == "COMPLETED_WITH_ERRORS":
            print(f"{status_icon} {name}: {detail} ({rec_count} recs)")
        else:
            print(f"{status_icon} {name}: {status}")
            if detail:
                print(f"   Error: {detail}")

    print("\n" + "="*60)
    print("NEXT STEPS:")
    print("="*60)
    print("1. Process results: uv run python scripts/harvest.py")
    print("2. Execute trades:  uv run python scripts/execute_recommendations.py <REQUEST_ID> <STRATEGY_ID> --provider-id gemini")
    print("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
