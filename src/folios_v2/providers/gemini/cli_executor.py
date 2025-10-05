"""CLI executor for the Gemini tool."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from folios_v2.providers import CliExecutor, CliResult, ExecutionTaskContext, SerializeResult
from folios_v2.providers.exceptions import ExecutionError


@dataclass(slots=True)
class GeminiCliExecutor(CliExecutor):
    """Execute research via the `gemini` CLI binary."""

    base_command: Sequence[str] = ("gemini", "--output-format", "json", "-y")

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
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()
        exit_code = process.returncode if process.returncode is not None else 0

        stderr_path: Path | None = None
        stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

        response_payload: dict[str, object] = {
            "provider": "gemini",
            "prompt": prompt,
            "exit_code": exit_code,
            "command": command,
        }

        parsed_cli_output: dict[str, object] | None = None
        if stdout_text:
            try:
                candidate = json.loads(stdout_text)
            except json.JSONDecodeError:
                response_payload["raw_stdout"] = stdout_text
            else:
                if isinstance(candidate, dict):
                    parsed_cli_output = candidate
                    response_payload["cli_output"] = candidate
                else:
                    response_payload["raw_stdout"] = stdout_text

        structured_payload = None
        if parsed_cli_output is not None:
            response_field = parsed_cli_output.get("response")
            if isinstance(response_field, str):
                structured_payload = _extract_structured_json(response_field)
                if structured_payload is not None:
                    response_payload["structured"] = structured_payload

        if stderr_text:
            response_payload["stderr"] = stderr_text
            stderr_path = artifact_dir / "stderr.txt"
            stderr_path.write_text(stderr_text, encoding="utf-8")

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
                "structured_path": str(structured_path)
                if structured_path is not None
                else None,
            },
        )


def _extract_structured_json(response_text: str) -> dict[str, object] | None:
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
        parsed: dict[str, object] = json.loads(raw_block)
    except json.JSONDecodeError:
        return None
    return parsed


__all__ = ["GeminiCliExecutor"]
