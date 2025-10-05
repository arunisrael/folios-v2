from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from uuid import UUID, uuid4

from folios_v2.domain import (
    ExecutionMode,
    ExecutionTask,
    LifecycleState,
    ProviderId,
    Request,
    RequestPriority,
    RequestType,
)
from folios_v2.providers.anthropic import AnthropicCliExecutor
from folios_v2.providers.gemini import GeminiCliExecutor
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.providers.openai import CodexCliExecutor


def _request_with_prompt(prompt: str, provider: ProviderId) -> Request:
    return Request(
        id=uuid4(),
        strategy_id=uuid4(),
        provider_id=provider,
        mode=ExecutionMode.CLI,
        request_type=RequestType.RESEARCH,
        priority=RequestPriority.NORMAL,
        metadata={"strategy_prompt": prompt},
    )


def _task(request_id: UUID) -> ExecutionTask:
    return ExecutionTask(
        id=uuid4(),
        request_id=request_id,
        sequence=1,
        mode=ExecutionMode.CLI,
        lifecycle_state=LifecycleState.PENDING,
    )


def _create_mock_cli(tmp_path: Path, label: str) -> Path:
    script = tmp_path / f"mock_{label}.py"
    script.write_text(
        """#!/usr/bin/env python3\nimport sys\nprint(f'PROMPT:{sys.argv[-1]}')\n""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_codex_cli_executor_runs(tmp_path: Path) -> None:
    script = _create_mock_cli(tmp_path, "codex")
    executor = CodexCliExecutor(base_command=(sys.executable, str(script), "exec"))

    request = _request_with_prompt("alpha analysis", ProviderId.OPENAI)
    task = _task(request.id)
    ctx = ExecutionTaskContext(
        request=request,
        task=task,
        artifact_dir=tmp_path / "artifacts" / "codex",
    )

    result = asyncio.run(executor.run(ctx, None))
    assert result.exit_code == 0
    assert result.stdout_path is not None
    assert result.stdout_path.read_text(encoding="utf-8").strip() == "PROMPT:alpha analysis"
    assert (ctx.artifact_dir / "prompt.txt").exists()


def test_gemini_cli_executor_runs(tmp_path: Path) -> None:
    script = _create_mock_cli(tmp_path, "gemini")
    executor = GeminiCliExecutor(base_command=(sys.executable, str(script), "-p"))

    request = _request_with_prompt("beta analysis", ProviderId.GEMINI)
    task = _task(request.id)
    ctx = ExecutionTaskContext(
        request=request,
        task=task,
        artifact_dir=tmp_path / "artifacts" / "gemini",
    )

    result = asyncio.run(executor.run(ctx, None))
    assert result.exit_code == 0
    assert result.stdout_path is not None
    assert result.stdout_path.read_text(encoding="utf-8").strip() == "PROMPT:beta analysis"
    assert (ctx.artifact_dir / "prompt.txt").exists()


def test_anthropic_cli_executor_runs(tmp_path: Path) -> None:
    script = _create_mock_cli(tmp_path, "anthropic")
    executor = AnthropicCliExecutor(
        base_command=(sys.executable, str(script), "--prompt")
    )

    request = _request_with_prompt("gamma analysis", ProviderId.ANTHROPIC)
    task = _task(request.id)
    ctx = ExecutionTaskContext(
        request=request,
        task=task,
        artifact_dir=tmp_path / "artifacts" / "anthropic",
    )

    result = asyncio.run(executor.run(ctx, None))
    assert result.exit_code == 0
    assert result.stdout_path is not None
    assert result.stdout_path.read_text(encoding="utf-8").strip() == "PROMPT:gamma analysis"
    assert (ctx.artifact_dir / "prompt.txt").exists()
