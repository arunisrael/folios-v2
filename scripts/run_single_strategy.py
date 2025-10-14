#!/usr/bin/env python3
"""
Execute a single strategy across multiple providers with flexible batch/CLI mode selection.

This script provides a unified interface for running one strategy through:
- Batch API (OpenAI, Gemini) - queued for async processing
- CLI executors (OpenAI Codex, Gemini, Anthropic Claude) - immediate execution

All executions create proper database entries (requests + tasks) that integrate
with the existing harvest/execute workflow.
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

import typer
from dotenv import load_dotenv

# Load .env file before importing folios modules
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

app = typer.Typer(help="Execute a single strategy across multiple providers")


async def _submit_batch_request(
    strategy_id: str,
    provider_id: str,
) -> tuple[str, str]:
    """Submit a batch request for a strategy and return (request_id, task_id)."""
    container = get_container()

    provider_enum = ProviderId(provider_id)
    strategy_uuid = StrategyId(UUID(strategy_id))

    async with container.unit_of_work_factory() as uow:
        strategy = await uow.strategy_repository.get(strategy_uuid)
        if strategy is None:
            typer.echo(f"Strategy {strategy_id} not found", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"\n[BATCH] {provider_id.upper()}: {strategy.name}")

        # Check if provider supports batch mode
        try:
            plugin = container.provider_registry.require(provider_enum, ExecutionMode.BATCH)
        except Exception as e:
            typer.echo(f"  ✗ Provider {provider_id} does not support batch mode: {e}", err=True)
            raise typer.Exit(code=1)

        if not plugin.supports_batch:
            typer.echo(f"  ✗ Provider {provider_id} does not support batch mode")
            raise typer.Exit(code=1)

        # Enqueue the request
        request, task = await container.request_orchestrator.enqueue_request(
            strategy,
            provider_id=provider_enum,
            request_type=RequestType.RESEARCH,
            mode=ExecutionMode.BATCH,
            priority=RequestPriority.NORMAL,
            scheduled_for=utc_now(),
            metadata={"triggered_by": "run_single_strategy_script"},
        )

        await uow.commit()

        typer.echo("  ✓ Batch request queued")
        typer.echo(f"    Request ID: {request.id}")
        typer.echo(f"    Task ID: {task.id}")

        return str(request.id), str(task.id)


async def _run_cli_executor(
    strategy_id: str,
    provider_id: str,
) -> tuple[str, str, dict[str, Any]]:
    """
    Execute CLI for a strategy, create database entries, and return
    (request_id, task_id, execution_result).
    """
    container = get_container()

    provider_enum = ProviderId(provider_id)
    strategy_uuid = StrategyId(UUID(strategy_id))

    async with container.unit_of_work_factory() as uow:
        strategy = await uow.strategy_repository.get(strategy_uuid)
        if strategy is None:
            typer.echo(f"Strategy {strategy_id} not found", err=True)
            raise typer.Exit(code=1)

        typer.echo(f"\n[CLI] {provider_id.upper()}: {strategy.name}")

        # Check if provider supports CLI mode
        try:
            plugin = container.provider_registry.require(provider_enum, ExecutionMode.CLI)
        except Exception as e:
            typer.echo(f"  ✗ Provider {provider_id} does not support CLI mode: {e}", err=True)
            raise typer.Exit(code=1)

        if not plugin.supports_cli:
            typer.echo(f"  ✗ Provider {provider_id} does not support CLI mode")
            raise typer.Exit(code=1)

        # Enqueue the request (creates database entries)
        request, task = await container.request_orchestrator.enqueue_request(
            strategy,
            provider_id=provider_enum,
            request_type=RequestType.RESEARCH,
            mode=ExecutionMode.CLI,
            priority=RequestPriority.NORMAL,
            scheduled_for=utc_now(),
            metadata={"triggered_by": "run_single_strategy_script"},
        )

        await uow.commit()

        typer.echo("  ✓ Request created in database")
        typer.echo(f"    Request ID: {request.id}")
        typer.echo(f"    Task ID: {task.id}")

    # Execute CLI immediately
    artifact_dir = container.settings.artifacts_root / str(request.id) / str(task.id)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    ctx = ExecutionTaskContext(
        request=request,
        task=task,
        artifact_dir=artifact_dir,
    )

    typer.echo("  → Executing CLI command...")
    result = await container.cli_runtime.run(plugin, ctx)

    typer.echo("  ✓ CLI execution completed")
    typer.echo(f"    Exit Code: {result.result.exit_code}")
    typer.echo(f"    Artifact Dir: {artifact_dir}")

    # Parse results using unified parser
    unified_parser = UnifiedResultParser(provider_id)
    parsed = await unified_parser.parse(ctx)
    parsed["cli_exit_code"] = result.result.exit_code

    # Save parsed results
    parsed_path = artifact_dir / "parsed.json"
    parsed_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
    typer.echo(f"    Parsed results: {parsed_path}")

    execution_result = {
        "request_id": str(request.id),
        "task_id": str(task.id),
        "provider_id": provider_id,
        "exit_code": result.result.exit_code,
        "artifact_dir": str(artifact_dir),
        "parsed_recommendations": parsed.get("recommendations", []),
    }

    return str(request.id), str(task.id), execution_result


async def _run_strategy(
    strategy_id: str,
    batch_providers: list[str],
    cli_providers: list[str],
) -> dict[str, Any]:
    """Execute strategy across specified batch and CLI providers."""
    container = get_container()

    # Validate strategy exists
    strategy_uuid = StrategyId(UUID(strategy_id))
    async with container.unit_of_work_factory() as uow:
        strategy = await uow.strategy_repository.get(strategy_uuid)
        if strategy is None:
            typer.echo(f"Strategy {strategy_id} not found", err=True)
            raise typer.Exit(code=1)

    typer.echo("=" * 80)
    typer.echo(f"Executing Strategy: {strategy.name}")
    typer.echo(f"Strategy ID: {strategy_id}")
    typer.echo(f"Batch Providers: {', '.join(batch_providers) if batch_providers else 'None'}")
    typer.echo(f"CLI Providers: {', '.join(cli_providers) if cli_providers else 'None'}")
    typer.echo("=" * 80)

    results = {
        "strategy_id": strategy_id,
        "strategy_name": strategy.name,
        "timestamp": datetime.now().isoformat(),
        "batch_submissions": [],
        "cli_executions": [],
    }

    # Submit batch requests
    for provider_id in batch_providers:
        try:
            request_id, task_id = await _submit_batch_request(strategy_id, provider_id)
            results["batch_submissions"].append({
                "provider_id": provider_id,
                "request_id": request_id,
                "task_id": task_id,
                "status": "submitted",
            })
        except Exception as e:
            typer.echo(f"  ✗ Batch submission failed: {e}", err=True)
            results["batch_submissions"].append({
                "provider_id": provider_id,
                "status": "failed",
                "error": str(e),
            })

    # Execute CLI requests
    for provider_id in cli_providers:
        try:
            request_id, task_id, execution_result = await _run_cli_executor(
                strategy_id, provider_id
            )
            results["cli_executions"].append({
                "provider_id": provider_id,
                "request_id": request_id,
                "task_id": task_id,
                "status": "completed",
                "exit_code": execution_result["exit_code"],
                "artifact_dir": execution_result["artifact_dir"],
                "recommendations_count": len(execution_result["parsed_recommendations"]),
            })
        except Exception as e:
            typer.echo(f"  ✗ CLI execution failed: {e}", err=True)
            results["cli_executions"].append({
                "provider_id": provider_id,
                "status": "failed",
                "error": str(e),
            })

    return results


@app.command()
def run(
    strategy_id: str = typer.Argument(..., help="Strategy UUID"),
    batch: str = typer.Option("", help="Comma-separated list of providers for BATCH mode (e.g., 'openai,gemini')"),
    cli: str = typer.Option("", help="Comma-separated list of providers for CLI mode (e.g., 'anthropic,gemini')"),
) -> None:
    """
    Execute a single strategy across multiple providers with flexible mode selection.

    Examples:
        # OpenAI batch + Gemini/Anthropic CLI
        python run_single_strategy.py STRATEGY_ID --batch openai --cli gemini,anthropic

        # All batch mode
        python run_single_strategy.py STRATEGY_ID --batch openai,gemini

        # All CLI mode
        python run_single_strategy.py STRATEGY_ID --cli openai,gemini,anthropic

        # Mixed execution
        python run_single_strategy.py STRATEGY_ID --batch openai,gemini --cli anthropic
    """
    batch_providers = [p.strip() for p in batch.split(",") if p.strip()]
    cli_providers = [p.strip() for p in cli.split(",") if p.strip()]

    if not batch_providers and not cli_providers:
        typer.echo("Error: Must specify at least one provider via --batch or --cli", err=True)
        raise typer.Exit(code=1)

    results = asyncio.run(_run_strategy(strategy_id, batch_providers, cli_providers))

    # Print summary
    typer.echo("\n" + "=" * 80)
    typer.echo("EXECUTION SUMMARY")
    typer.echo("=" * 80)

    if results["batch_submissions"]:
        typer.echo("\nBatch Submissions:")
        for submission in results["batch_submissions"]:
            provider = submission["provider_id"]
            status = submission["status"]
            if status == "submitted":
                typer.echo(f"  ✓ {provider}: {submission['request_id']}")
            else:
                typer.echo(f"  ✗ {provider}: {submission.get('error', 'unknown error')}")

    if results["cli_executions"]:
        typer.echo("\nCLI Executions:")
        for execution in results["cli_executions"]:
            provider = execution["provider_id"]
            status = execution["status"]
            if status == "completed":
                rec_count = execution["recommendations_count"]
                typer.echo(f"  ✓ {provider}: {execution['request_id']} ({rec_count} recommendations)")
            else:
                typer.echo(f"  ✗ {provider}: {execution.get('error', 'unknown error')}")

    typer.echo("\n" + "=" * 80)
    typer.echo("NEXT STEPS:")
    typer.echo("=" * 80)
    typer.echo("1. Check status:     make status")
    typer.echo("2. Harvest results:  make harvest")
    typer.echo("3. Execute trades:   uv run python scripts/execute_recommendations.py \\")
    typer.echo("                       <REQUEST_ID> <STRATEGY_ID> --provider-id <PROVIDER>")
    typer.echo("=" * 80)

    # Save results to file
    artifacts_dir = Path(__file__).parent.parent / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    results_file = artifacts_dir / f"run_single_{strategy_id[:8]}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    results_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
    typer.echo(f"\nResults saved to: {results_file}")


if __name__ == "__main__":
    app()
