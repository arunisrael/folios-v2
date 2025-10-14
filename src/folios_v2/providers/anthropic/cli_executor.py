"""CLI executor for Anthropic."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from folios_v2.providers import CliExecutor, CliResult, ExecutionTaskContext, SerializeResult
from folios_v2.providers.exceptions import ExecutionError


@dataclass(slots=True)
class AnthropicCliExecutor(CliExecutor):
    """Execute Anthropic research via the Claude CLI."""

    base_command: Sequence[str] = (
        "claude",
        "-p",
        "--output-format",
        "json",
        "--dangerously-skip-permissions",
    )

    async def run(
        self,
        ctx: ExecutionTaskContext,
        payload: SerializeResult | None = None,
    ) -> CliResult:
        _ = payload
        prompt = ctx.request.metadata.get("strategy_prompt")
        if not prompt:
            msg = "Strategy prompt missing from request metadata"
            raise ExecutionError(msg)

        artifact_dir = ctx.artifact_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = artifact_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        command = [*self.base_command, prompt]

        # Ensure environment variables are passed to subprocess
        # This is needed for non-interactive mode authentication
        import os
        env = os.environ.copy()

        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,  # Explicitly pass environment
        )
        stdout, stderr = await process.communicate()

        stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

        response_payload: dict[str, Any] = {
            "provider": "anthropic",
            "prompt": prompt,
            "command": command,
        }

        # Parse the JSON output from Claude CLI
        cli_output: dict[str, Any] | None = None
        if stdout_text:
            try:
                cli_output = json.loads(stdout_text)
            except json.JSONDecodeError:
                response_payload["raw_stdout"] = stdout_text

        # Extract the result field from Claude CLI output
        result_text: str | None = None
        structured_payload: dict[str, Any] | None = None

        if cli_output is not None:
            response_payload["cli_output"] = cli_output
            result_text = cli_output.get("result")

            if isinstance(result_text, str):
                response_payload["result"] = result_text
                # Try to parse the result as JSON directly
                try:
                    decoded = json.loads(result_text)
                    if isinstance(decoded, dict):
                        structured_payload = decoded
                except json.JSONDecodeError:
                    # If not direct JSON, try to extract from markdown blocks
                    structured_payload = _extract_structured_json(result_text)

        if structured_payload is not None:
            response_payload["structured"] = structured_payload

        stderr_path: Path | None = None
        if stderr_text:
            response_payload["stderr"] = stderr_text
            stderr_path = artifact_dir / "stderr.txt"
            stderr_path.write_text(stderr_text, encoding="utf-8")

        exit_code = process.returncode if process.returncode is not None else 0
        response_payload["exit_code"] = exit_code

        response_path = artifact_dir / "response.json"
        response_path.write_text(
            json.dumps(response_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        structured_path: Path | None = None
        if structured_payload is not None:
            structured_path = artifact_dir / "structured.json"
            structured_path.write_text(
                json.dumps(structured_payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return CliResult(
            exit_code=exit_code,
            stdout_path=None,
            stderr_path=stderr_path,
            metadata={
                "command": " ".join(command),
                "response_path": str(response_path),
                "structured_path": str(structured_path) if structured_path is not None else None,
            },
        )


def _extract_structured_json(response_text: str) -> dict[str, Any] | None:
    """Extract JSON from markdown code blocks in the response."""
    marker = "```json"
    start = response_text.find(marker)
    if start == -1:
        return None
    start = response_text.find("\n", start)
    if start == -1:
        return None
    start += 1
    end = response_text.find("```", start)
    if end == -1:
        return None
    raw_block = response_text[start:end].strip()
    try:
        parsed: dict[str, Any] = json.loads(raw_block)
    except json.JSONDecodeError:
        return None
    return parsed


__all__ = ["AnthropicCliExecutor"]
