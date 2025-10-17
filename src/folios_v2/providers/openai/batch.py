"""OpenAI batch-mode integration backed by the official REST API."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from folios_v2.providers import (
    BatchExecutor,
    ExecutionTaskContext,
    RequestSerializer,
    ResultParser,
    SerializeResult,
)
from folios_v2.providers.exceptions import (
    ExecutionError,
    ParseError,
    ProviderError,
    SerializationError,
)
from folios_v2.providers.models import DownloadResult, PollResult, SubmitResult
from folios_v2.schemas import OPENAI_RESPONSE_FORMAT

_OPENAI_BATCH_ENDPOINT = "/v1/batches"
_OPENAI_FILES_ENDPOINT = "/v1/files"
_DEFAULT_SYSTEM_MESSAGE = (
    "You are a research analyst returning JSON that conforms to the "
    "investment_analysis_v1 schema. Respond with valid JSON only."
)


@dataclass(slots=True)
class OpenAIProviderConfig:
    """Configuration bundle for OpenAI batch execution."""

    api_key: str | None = None
    model: str = field(default="gpt-4o-mini")
    endpoint: str = field(default="https://api.openai.com")
    completion_window: str = field(default="24h")
    system_message: str = field(default=_DEFAULT_SYSTEM_MESSAGE)
    allow_local_fallback: bool = field(default=True)

    @classmethod
    def from_env(cls) -> OpenAIProviderConfig:
        defaults = cls()
        return cls(
            api_key=os.getenv("OPENAI_API_KEY") or None,
            model=os.getenv("OPENAI_BATCH_MODEL", defaults.model),
            endpoint=os.getenv("OPENAI_API_BASE", defaults.endpoint),
            completion_window=os.getenv("OPENAI_COMPLETION_WINDOW", defaults.completion_window),
            system_message=os.getenv("OPENAI_BATCH_SYSTEM_MESSAGE", defaults.system_message),
            allow_local_fallback=(os.getenv("FOLIOS_LOCAL_BATCH_FALLBACK", "1") != "0"),
        )


class OpenAIRequestSerializer(RequestSerializer):
    """Serialize request metadata into a JSONL payload for the OpenAI batch endpoint."""

    def __init__(
        self,
        *,
        model: str,
        system_message: str,
        filename: str = "openai_payload.jsonl",
    ) -> None:
        self._model = model
        self._system_message = system_message
        self._filename = filename

    async def serialize(self, ctx: ExecutionTaskContext) -> SerializeResult:
        prompt = ctx.request.metadata.get("strategy_prompt")
        if not prompt:
            raise SerializationError(
                "strategy_prompt metadata is required for OpenAI batch submission"
            )

        payload_path = ctx.artifact_dir / self._filename
        payload_path.parent.mkdir(parents=True, exist_ok=True)

        batch_record = {
            "custom_id": str(ctx.task.id),
            "method": "POST",
            "url": "/v1/chat/completions",
            "body": {
                "model": self._model,
                "messages": [
                    {"role": "system", "content": self._system_message},
                    {"role": "user", "content": prompt},
                ],
                "response_format": deepcopy(OPENAI_RESPONSE_FORMAT),
            },
        }

        payload_path.write_text(json.dumps(batch_record), encoding="utf-8")

        return SerializeResult(
            payload_path=payload_path,
            content_type="application/jsonl",
            metadata={"records": 1, "model": self._model},
        )


class OpenAIBatchExecutor(BatchExecutor):
    """Submit, poll, and download OpenAI batch jobs via HTTP."""

    def __init__(
        self,
        *,
        api_key: str,
        endpoint: str = "https://api.openai.com",
        completion_window: str = "24h",
        request_timeout: float = 30.0,
    ) -> None:
        if not api_key:
            raise ProviderError("OpenAIBatchExecutor requires a valid API key")
        self._api_key = api_key
        self._endpoint = endpoint.rstrip("/")
        self._completion_window = completion_window
        self._request_timeout = request_timeout

    def _headers(self) -> Mapping[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._endpoint,
            timeout=self._request_timeout,
            headers=self._headers(),
        )

    async def submit(self, ctx: ExecutionTaskContext, payload: SerializeResult) -> SubmitResult:
        payload_path = Path(payload.payload_path)
        if not payload_path.exists():
            raise ExecutionError(f"Serialized payload not found at {payload_path}")

        async with self._client() as client:
            file_id = await self._upload_file(client, payload_path)
            body = {
                "input_file_id": file_id,
                "endpoint": "/v1/chat/completions",
                "completion_window": self._completion_window,
                "metadata": {
                    "request_id": str(ctx.request.id),
                    "task_id": str(ctx.task.id),
                },
            }
            response = await client.post(_OPENAI_BATCH_ENDPOINT, json=body)
            response.raise_for_status()
            data = response.json()

        job_id = data.get("id")
        if not job_id:
            raise ExecutionError("OpenAI batch submission did not return an id")

        # Validate batch ID format - OpenAI batch IDs should start with 'batch_'
        if not str(job_id).startswith("batch_"):
            raise ExecutionError(
                f"Invalid OpenAI batch ID format: '{job_id}'. "
                "Expected ID to start with 'batch_'. "
                "Full response: {data}"
            )

        metadata = {
            "input_file_id": file_id,
            "status": data.get("status"),
        }
        return SubmitResult(provider_job_id=str(job_id), metadata=metadata)

    async def _upload_file(self, client: httpx.AsyncClient, payload_path: Path) -> str:
        with payload_path.open("rb") as handle:
            files = {"file": (payload_path.name, handle, "application/jsonl")}
            data = {"purpose": "batch"}
            response = await client.post(_OPENAI_FILES_ENDPOINT, files=files, data=data)
        response.raise_for_status()
        result = response.json()
        file_id = result.get("id")
        if not file_id:
            raise ExecutionError("OpenAI file upload response missing id")
        return str(file_id)

    async def poll(self, ctx: ExecutionTaskContext, provider_job_id: str) -> PollResult:
        async with self._client() as client:
            response = await client.get(f"{_OPENAI_BATCH_ENDPOINT}/{provider_job_id}")
            response.raise_for_status()
            data = response.json()

        status = data.get("status", "in_progress")
        mapped_status = _map_openai_status(status)
        counts = data.get("request_counts") or {}
        metadata = {
            "status": status,
            "counts": counts,
            "output_file_id": data.get("output_file_id"),
            "error_file_id": data.get("error_file_id"),
        }
        completed = mapped_status == "completed"
        return PollResult(completed=completed, status=mapped_status, metadata=metadata)

    async def download(self, ctx: ExecutionTaskContext, provider_job_id: str) -> DownloadResult:
        async with self._client() as client:
            response = await client.get(f"{_OPENAI_BATCH_ENDPOINT}/{provider_job_id}")
            response.raise_for_status()
            data = response.json()
            status = data.get("status")
            if status != "completed":
                raise ExecutionError(
                    f"OpenAI batch {provider_job_id} not completed (status={status or 'unknown'})"
                )
            output_file_id = data.get("output_file_id")
            if not output_file_id:
                raise ExecutionError(f"OpenAI batch {provider_job_id} missing output file id")

            content = await client.get(f"{_OPENAI_FILES_ENDPOINT}/{output_file_id}/content")
            content.raise_for_status()
            artifact_path = ctx.artifact_dir / "openai_batch_results.jsonl"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)
            artifact_path.write_bytes(content.content)

        metadata = {
            "output_file_id": output_file_id,
            "provider_job_id": provider_job_id,
        }
        return DownloadResult(
            artifact_path=artifact_path,
            content_type="application/jsonl",
            metadata=metadata,
        )


def _map_openai_status(status: str) -> str:
    mapping = {
        "validating": "processing",
        "in_progress": "processing",
        "finalizing": "processing",
        "completed": "completed",
        "failed": "failed",
        "expired": "timeout",
        "cancelling": "processing",
        "cancelled": "cancelled",
    }
    return mapping.get(status, "processing")


class OpenAIResultParser(ResultParser):
    """Parse the downloaded OpenAI JSONL results into a canonical dictionary."""

    def __init__(self, results_filename: str = "openai_batch_results.jsonl") -> None:
        self._results_filename = results_filename

    async def parse(self, ctx: ExecutionTaskContext) -> Mapping[str, Any]:
        results_path = ctx.artifact_dir / self._results_filename
        if not results_path.exists():
            raise ParseError(f"OpenAI results file not found at {results_path}")

        records: list[dict[str, Any]] = []
        with results_path.open(encoding="utf-8") as handle:
            for raw in handle:
                line = raw.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ParseError(f"Malformed JSON in OpenAI results: {exc}") from exc
                records.append(payload)

        summary = {
            "provider": "openai",
            "request_id": str(ctx.request.id),
            "task_id": str(ctx.task.id),
            "strategy_id": str(ctx.request.strategy_id),
            "prompt": ctx.request.metadata.get("strategy_prompt"),
            "total": len(records),
            "records": records,
        }
        return summary


__all__ = [
    "OpenAIBatchExecutor",
    "OpenAIProviderConfig",
    "OpenAIRequestSerializer",
    "OpenAIResultParser",
]
