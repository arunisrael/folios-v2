"""Local batch execution helpers used for provider simulations."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from folios_v2.domain.enums import ProviderId
from folios_v2.providers import (
    BatchExecutor,
    ExecutionTaskContext,
    ProviderError,
    RequestSerializer,
    ResultParser,
    SerializeResult,
)
from folios_v2.providers.exceptions import ParseError, SerializationError
from folios_v2.providers.models import DownloadResult, PollResult, SubmitResult


class LocalJSONRequestSerializer(RequestSerializer):
    """Serialize prompts into JSON payloads for local batch simulation."""

    def __init__(self, provider_id: ProviderId, filename: str = "payload.json") -> None:
        self._provider_id = provider_id
        self._filename = filename

    async def serialize(self, ctx: ExecutionTaskContext) -> SerializeResult:
        prompt = ctx.request.metadata.get("strategy_prompt")
        if not prompt:
            msg = "strategy_prompt metadata is required for batch serialization"
            raise SerializationError(msg)

        data = {
            "provider": self._provider_id.value,
            "strategy_id": str(ctx.request.strategy_id),
            "task_id": str(ctx.task.id),
            "prompt": prompt,
        }
        payload_path = ctx.artifact_dir / self._filename
        payload_path.parent.mkdir(parents=True, exist_ok=True)
        payload_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return SerializeResult(
            payload_path=payload_path,
            content_type="application/json",
            metadata=data,
        )


class LocalJSONBatchExecutor(BatchExecutor):
    """Simulated batch executor that echoes prompts into provider-specific JSON results."""

    def __init__(self, provider_id: ProviderId, response_filename: str = "response.json") -> None:
        self._provider_id = provider_id
        self._response_filename = response_filename
        self._responses: dict[str, Path] = {}

    async def submit(self, ctx: ExecutionTaskContext, payload: SerializeResult) -> SubmitResult:
        payload_path_str = str(payload.payload_path)
        try:
            payload_data = json.loads(payload.payload_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise SerializationError(f"Invalid payload JSON: {exc}") from exc

        job_id = f"{ctx.task.id}-{uuid4().hex[:8]}"
        response = {
            "provider": self._provider_id.value,
            "strategy_id": payload_data.get("strategy_id"),
            "task_id": str(ctx.task.id),
            "prompt": payload_data.get("prompt"),
        }
        response_path = ctx.artifact_dir / self._response_filename
        response_path.parent.mkdir(parents=True, exist_ok=True)
        response_path.write_text(
            json.dumps(response, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._responses[job_id] = response_path
        metadata = {"payload_path": payload_path_str, "response_path": str(response_path)}
        return SubmitResult(provider_job_id=job_id, metadata=metadata)

    async def poll(self, ctx: ExecutionTaskContext, provider_job_id: str) -> PollResult:
        completed = provider_job_id in self._responses
        status = "succeeded" if completed else "pending"
        return PollResult(completed=completed, status=status)

    async def download(self, ctx: ExecutionTaskContext, provider_job_id: str) -> DownloadResult:
        try:
            path = self._responses[provider_job_id]
        except KeyError as exc:
            raise ProviderError(f"Unknown provider job id: {provider_job_id}") from exc
        return DownloadResult(artifact_path=path, content_type="application/json")


class LocalJSONParser(ResultParser):
    """Parse batch or CLI outputs into structured dictionaries."""

    def __init__(self, response_filename: str = "response.json") -> None:
        self._response_filename = response_filename

    async def parse(self, ctx: ExecutionTaskContext) -> dict[str, object]:
        if ctx.task.stdout_path:
            stdout_path = Path(ctx.task.stdout_path)
            return {"raw_text": stdout_path.read_text(encoding="utf-8")}

        structured_path = ctx.artifact_dir / "structured.json"
        if structured_path.exists():
            try:
                structured: dict[str, Any] = json.loads(
                    structured_path.read_text(encoding="utf-8")
                )
                return structured
            except json.JSONDecodeError as exc:
                raise ParseError(f"Invalid structured JSON output: {exc}") from exc

        response_path = ctx.artifact_dir / self._response_filename
        if not response_path.exists():
            raise ParseError(f"Expected response file at {response_path}")
        try:
            data: dict[str, Any] = json.loads(
                response_path.read_text(encoding="utf-8")
            )
            structured = data.get("structured") if isinstance(data, dict) else None
            if isinstance(structured, dict):
                return structured
            return data
        except json.JSONDecodeError as exc:
            raise ParseError(f"Invalid JSON output: {exc}") from exc


__all__ = [
    "LocalJSONBatchExecutor",
    "LocalJSONParser",
    "LocalJSONRequestSerializer",
]
