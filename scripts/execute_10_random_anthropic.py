#!/usr/bin/env python3
"""Execute 10 random strategies inline using Anthropic provider within Claude's context."""

import asyncio
import json
import random
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

# Load .env file
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, RequestPriority, RequestType
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.types import StrategyId
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.providers.unified_parser import UnifiedResultParser
from folios_v2.utils import utc_now


async def execute_strategy_inline(strategy_data: dict) -> dict:
    """Execute a single strategy inline using Anthropic CLI provider."""
    container = get_container()
    strategy_id = StrategyId(UUID(strategy_data["id"]))

    async with container.unit_of_work_factory() as uow:
        strategy = await uow.strategy_repository.get(strategy_id)
        if strategy is None:
            return {
                "strategy_id": strategy_data["id"],
                "strategy_name": strategy_data["name"],
                "status": "error",
                "error": "Strategy not found in database"
            }

        print(f"\n{'='*80}")
        print(f"Executing: {strategy.name}")
        print(f"ID: {strategy_id}")
        print(f"{'='*80}")

        # Create request and task
        request, task = await container.request_orchestrator.enqueue_request(
            strategy,
            provider_id=ProviderId.ANTHROPIC,
            request_type=RequestType.RESEARCH,
            mode=ExecutionMode.CLI,
            priority=RequestPriority.NORMAL,
            scheduled_for=utc_now(),
            metadata={"triggered_by": "execute_10_random_anthropic", "inline_execution": "true"},
        )

        await uow.commit()

        print(f"✓ Request created: {request.id}")
        print(f"✓ Task created: {task.id}")

    # Get Anthropic CLI plugin
    plugin = container.provider_registry.require(ProviderId.ANTHROPIC, ExecutionMode.CLI)

    # Setup artifact directory
    artifact_dir = container.settings.artifacts_root / str(request.id) / str(task.id)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    # Create execution context
    ctx = ExecutionTaskContext(
        request=request,
        task=task,
        artifact_dir=artifact_dir,
    )

    print("→ Executing Anthropic CLI...")

    # Execute
    result = await container.cli_runtime.run(plugin, ctx)

    print(f"✓ Execution completed (exit code: {result.result.exit_code})")

    # Parse results
    unified_parser = UnifiedResultParser(ProviderId.ANTHROPIC.value)
    parsed = await unified_parser.parse(ctx)
    parsed["cli_exit_code"] = result.result.exit_code

    # Save parsed results
    parsed_path = artifact_dir / "parsed.json"
    parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")

    recommendations = parsed.get("recommendations", [])
    print(f"✓ Recommendations: {len(recommendations)}")

    # Print summary of recommendations
    if recommendations:
        print("\n  Top Recommendations:")
        for i, rec in enumerate(recommendations[:3], 1):
            ticker = rec.get("ticker", "N/A")
            action = rec.get("action", "N/A")
            confidence = rec.get("confidence", "N/A")
            print(f"    {i}. {ticker} - {action} (confidence: {confidence})")

    return {
        "strategy_id": str(strategy_id),
        "strategy_name": strategy.name,
        "status": "success",
        "request_id": str(request.id),
        "task_id": str(task.id),
        "exit_code": result.result.exit_code,
        "artifact_dir": str(artifact_dir),
        "recommendation_count": len(recommendations),
        "recommendations": recommendations[:5],  # Store top 5
    }


async def main():
    """Main execution function."""
    # Load strategy data
    data_file = Path(__file__).parent.parent / "data" / "strategy_screener_mapping.json"
    with open(data_file) as f:
        all_strategies = json.load(f)

    # Randomly select 10 strategies
    random.seed(42)  # For reproducibility
    selected_strategies = random.sample(all_strategies, 10)

    print(f"\n{'='*80}")
    print("EXECUTING 10 RANDOM STRATEGIES WITH ANTHROPIC PROVIDER")
    print(f"{'='*80}")
    print("\nSelected Strategies:")
    for i, s in enumerate(selected_strategies, 1):
        print(f"  {i}. {s['name']} ({s['id'][:8]}...)")

    # Execute all strategies
    results = []
    for strategy_data in selected_strategies:
        try:
            result = await execute_strategy_inline(strategy_data)
            results.append(result)
        except Exception as e:
            print(f"\n✗ Error executing {strategy_data['name']}: {e}")
            results.append({
                "strategy_id": strategy_data["id"],
                "strategy_name": strategy_data["name"],
                "status": "error",
                "error": str(e)
            })

    # Print final summary
    print(f"\n{'='*80}")
    print("EXECUTION SUMMARY")
    print(f"{'='*80}")

    successful = sum(1 for r in results if r["status"] == "success")
    failed = sum(1 for r in results if r["status"] == "error")

    print(f"\nTotal Executed: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")

    if successful > 0:
        total_recs = sum(r.get("recommendation_count", 0) for r in results if r["status"] == "success")
        print(f"Total Recommendations: {total_recs}")

    print("\nDetailed Results:")
    for i, r in enumerate(results, 1):
        status_icon = "✓" if r["status"] == "success" else "✗"
        name = r["strategy_name"]
        if r["status"] == "success":
            rec_count = r.get("recommendation_count", 0)
            print(f"  {status_icon} {i}. {name}: {rec_count} recommendations")
        else:
            error = r.get("error", "Unknown error")
            print(f"  {status_icon} {i}. {name}: {error}")

    # Save results
    output_file = Path(__file__).parent.parent / "artifacts" / "execute_10_random_anthropic_results.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")

    print(f"\n{'='*80}")
    print(f"Results saved to: {output_file}")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
