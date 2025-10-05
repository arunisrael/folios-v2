"""CLI executor for Anthropic."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from folios_v2.providers import CliExecutor, CliResult, ExecutionTaskContext, SerializeResult
from folios_v2.providers.exceptions import ExecutionError


@dataclass(slots=True)
class AnthropicCliExecutor(CliExecutor):
    """Execute Anthropic research via a local CLI binary."""

    base_command: Sequence[str] = ("anthropic", "--prompt")

    async def run(
        self,
        ctx: ExecutionTaskContext,
        payload: SerializeResult | None = None,
    ) -> CliResult:
        prompt = ctx.request.metadata.get("strategy_prompt")
        if not prompt:
            msg = "Strategy prompt missing from request metadata"
            raise ExecutionError(msg)

        artifact_dir = ctx.artifact_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = artifact_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        command = [*self.base_command, prompt]
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        stdout_path: Path | None = None
        stderr_path: Path | None = None
        if stdout:
            stdout_path = artifact_dir / "stdout.txt"
            stdout_path.write_bytes(stdout)
        if stderr:
            stderr_path = artifact_dir / "stderr.txt"
            stderr_path.write_bytes(stderr)

        exit_code = process.returncode if process.returncode is not None else 0
        return CliResult(
            exit_code=exit_code,
            stdout_path=stdout_path,
            stderr_path=stderr_path,
            metadata={"command": " ".join(command)},
        )


__all__ = ["AnthropicCliExecutor"]
