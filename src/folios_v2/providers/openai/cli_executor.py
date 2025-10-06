"""CLI executor for the OpenAI Codex tool."""

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
class CodexCliExecutor(CliExecutor):
    """Execute OpenAI research via the local `codex` CLI."""

    base_command: Sequence[str] = (
        "codex",
        "--search",
        "exec",
        "--json",
        "--skip-git-repo-check",
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
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate()

        stdout_text = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_text = stderr.decode("utf-8", errors="replace") if stderr else ""

        if stdout_text:
            (artifact_dir / "stdout.txt").write_text(stdout_text, encoding="utf-8")

        response_payload: dict[str, Any] = {
            "provider": "openai",
            "prompt": prompt,
            "command": command,
        }

        events = _parse_event_stream(stdout_text)
        if events:
            response_payload["events"] = events

        agent_text = _extract_agent_text(events)
        structured_payload: dict[str, Any] | None = None
        if agent_text is not None:
            response_payload["agent_text"] = agent_text
            try:
                decoded = json.loads(agent_text)
            except json.JSONDecodeError:
                structured_payload = _extract_structured_json(agent_text)
            else:
                if isinstance(decoded, dict):
                    structured_payload = decoded
                else:
                    response_payload["agent_parsed"] = decoded
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
                "structured_path": str(structured_path)
                if structured_path is not None
                else None,
            },
        )


def _parse_event_stream(output: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for line in output.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            events.append(parsed)
    return events


def _extract_agent_text(events: list[dict[str, Any]]) -> str | None:
    for event in reversed(events):
        if event.get("type") != "item.completed":
            continue
        item = event.get("item")
        if not isinstance(item, dict):
            continue
        if item.get("type") != "agent_message":
            continue
        text = item.get("text")
        if isinstance(text, str):
            return text
        content = item.get("content")
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if not isinstance(part, dict):
                    continue
                segment = part.get("text")
                if isinstance(segment, str):
                    parts.append(segment)
            if parts:
                return "".join(parts)
    return None


def _extract_structured_json(response_text: str) -> dict[str, Any] | None:
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


__all__ = ["CodexCliExecutor"]
