"""Gemini batch-mode integration using the google-genai Batch API."""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types as genai_types

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
from folios_v2.schemas import INVESTMENT_ANALYSIS_SCHEMA

_DEFAULT_SYSTEM_INSTRUCTIONS = (
    "Return only valid JSON conforming to the provided schema. No markdown, no prose. "
    "If a value is unknown, use null (don't invent). All strings must be UTF-8; escape "
    "newlines and quotes. Dates must be ISO-8601 (YYYY-MM-DD). Use enum values exactly "
    "as listed; otherwise fail. Do not include trailing commas. Trading eligibility and "
    "symbol validity: Only recommend currently listed, tradeable U.S. equities (NYSE, "
    "Nasdaq, NYSE American). Exclude OTC/pink sheet and delisted symbols. Do not invent "
    "or use placeholder/generic tickers (e.g., ABC, TEST). Company names must match the "
    "ticker's real company. Before adding any recommendation, confirm the ticker remains "
    "active on those exchanges and has not recently changed symbols or been delisted. If "
    "no valid symbols qualify, return an empty recommendations array. Recency: Prioritize "
    "information from 2025 Q2 onward (especially Q3 2025)."
)


@dataclass(slots=True)
class GeminiProviderConfig:
    """Configuration bundle for Gemini batch execution."""

    api_key: str | None = None
    model: str = field(default="gemini-2.5-pro")
    allow_local_fallback: bool = field(default=True)

    @classmethod
    def from_env(cls) -> GeminiProviderConfig:
        defaults = cls()
        return cls(
            api_key=os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or None,
            model=os.getenv("GEMINI_BATCH_MODEL", defaults.model),
            allow_local_fallback=(os.getenv("FOLIOS_LOCAL_BATCH_FALLBACK", "1") != "0"),
        )


class GeminiRequestSerializer(RequestSerializer):
    """Serialize requests into Gemini batch JSON payloads."""

    def __init__(
        self,
        *,
        model: str,
        instructions: str = _DEFAULT_SYSTEM_INSTRUCTIONS,
        filename: str = "gemini_payload.json",
    ) -> None:
        self._model = model
        self._instructions = instructions
        self._filename = filename

        self._response_schema = _clean_schema_for_gemini(INVESTMENT_ANALYSIS_SCHEMA["schema"])  # type: ignore[index]

    async def serialize(self, ctx: ExecutionTaskContext) -> SerializeResult:
        prompt = ctx.request.metadata.get("strategy_prompt")
        if not prompt:
            raise SerializationError(
                "strategy_prompt metadata is required for Gemini batch submission"
            )

        prompt_text = f"{self._instructions}\n\n{prompt}" if self._instructions else prompt
        payload_path = ctx.artifact_dir / self._filename
        payload_path.parent.mkdir(parents=True, exist_ok=True)

        record = {
            "requests": [
                {
                    "custom_id": str(ctx.task.id),
                    "prompt": prompt,
                    "payload": {
                        "model": self._model,
                        "contents": [
                            {
                                "role": "user",
                                "parts": [{"text": prompt_text}],
                            }
                        ],
                        "generationConfig": {
                            "responseMimeType": "application/json",
                            "responseSchema": self._response_schema,
                        },
                    },
                }
            ]
        }

        payload_path.write_text(json.dumps(record, indent=2), encoding="utf-8")

        return SerializeResult(
            payload_path=payload_path,
            content_type="application/json",
            metadata={"model": self._model, "records": 1},
        )


class GeminiBatchExecutor(BatchExecutor):
    """Submit, poll, and download Gemini batch jobs via the google-genai client."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-2.5-pro",
        request_timeout: float = 600.0,
    ) -> None:
        if not api_key:
            raise ProviderError("GeminiBatchExecutor requires a valid API key")
        self._api_key = api_key
        self._model = _normalize_model(model)
        self._request_timeout = request_timeout
        self._meta: dict[str, dict[str, Any]] = {}

    def _client(self) -> genai.Client:
        # Google genai SDK expects timeout in milliseconds, not seconds
        timeout_ms = int(self._request_timeout * 1000)
        return genai.Client(api_key=self._api_key, http_options={"timeout": timeout_ms})

    async def submit(self, ctx: ExecutionTaskContext, payload: SerializeResult) -> SubmitResult:
        payload_path = Path(payload.payload_path)
        if not payload_path.exists():
            raise ExecutionError(f"Serialized payload not found at {payload_path}")

        def _submit() -> SubmitResult:
            with payload_path.open(encoding="utf-8") as handle:
                data = json.load(handle)

            requests = data.get("requests") if isinstance(data, dict) else data
            if not isinstance(requests, list) or not requests:
                raise ExecutionError("Gemini payload must include a non-empty 'requests' list")

            inlined_requests: list[genai_types.InlinedRequest] = []
            custom_ids: list[str] = []

            for item in requests:
                payload = item.get("payload") or {}
                contents = payload.get("contents") or []
                generation_cfg = payload.get("generationConfig") or {}
                model_name = _normalize_model(payload.get("model") or self._model)

                typed_contents = [genai_types.Content(**part) for part in contents]

                cfg_kwargs = dict(generation_cfg)
                config = genai_types.GenerateContentConfig(**cfg_kwargs) if cfg_kwargs else None

                inlined_requests.append(
                    genai_types.InlinedRequest(
                        model=model_name,
                        contents=typed_contents,
                        config=config,
                    )
                )

                custom_id = (item.get("custom_id") or "").strip()
                custom_ids.append(custom_id)

            client = self._client()
            job = client.batches.create(
                model=_normalize_model(self._model),
                src=inlined_requests,
                config=genai_types.CreateBatchJobConfig(display_name=f"folios-batch-{ctx.task.id}"),
            )
            job_name = getattr(job, "name", None)
            if not job_name:
                raise ExecutionError("Gemini batch submission did not return a job name")

            self._meta[job_name] = {"custom_ids": custom_ids}
            return SubmitResult(provider_job_id=str(job_name), metadata={"custom_ids": custom_ids})

        return await asyncio.to_thread(_submit)

    async def poll(self, ctx: ExecutionTaskContext, provider_job_id: str) -> PollResult:
        def _poll() -> PollResult:
            client = self._client()
            job = client.batches.get(name=provider_job_id)
            state = getattr(getattr(job, "state", None), "name", "JOB_STATE_RUNNING")
            counts = getattr(job, "batch_stats", None)
            metadata = {
                "status": state,
                "counts": {
                    "total": getattr(counts, "total_requests", 0) if counts else 0,
                    "completed": getattr(counts, "completed_requests", 0) if counts else 0,
                    "failed": getattr(counts, "failed_requests", 0) if counts else 0,
                },
            }
            mapped = _map_gemini_status(state)
            return PollResult(completed=mapped == "completed", status=mapped, metadata=metadata)

        return await asyncio.to_thread(_poll)

    async def download(self, ctx: ExecutionTaskContext, provider_job_id: str) -> DownloadResult:
        def _download() -> DownloadResult:
            client = self._client()
            job = client.batches.get(name=provider_job_id)
            state = getattr(getattr(job, "state", None), "name", "")
            if state != "JOB_STATE_SUCCEEDED":
                raise ExecutionError(
                    f"Gemini batch {provider_job_id} not completed (state={state or 'unknown'})"
                )

            dest = getattr(job, "dest", None)
            responses = getattr(dest, "inlined_responses", None) or []

            custom_ids = self._meta.get(provider_job_id, {}).get("custom_ids", [])
            artifact_path = ctx.artifact_dir / "gemini_batch_results.jsonl"
            artifact_path.parent.mkdir(parents=True, exist_ok=True)

            with artifact_path.open("w", encoding="utf-8") as handle:
                for idx, item in enumerate(responses):
                    text: str | None = None
                    if hasattr(item, "response"):
                        response = item.response
                        text = getattr(response, "text", None)
                    elif isinstance(item, dict):
                        response = item.get("response")
                        if isinstance(response, dict):
                            text = response.get("text")

                    if text is None:
                        try:
                            text = json.dumps(item)
                        except Exception:
                            text = str(item)

                    record = {
                        "custom_id": custom_ids[idx] if idx < len(custom_ids) else None,
                        "response": {
                            "status_code": 200,
                            "body": {
                                "candidates": [
                                    {
                                        "content": {"parts": [{"text": text}]},
                                        "index": 0,
                                        "finishReason": "STOP",
                                    }
                                ]
                            },
                        },
                        "error": None,
                    }
                    handle.write(json.dumps(record) + "\n")

                if not responses:
                    handle.write(
                        json.dumps(
                            {
                                "custom_id": custom_ids[0] if custom_ids else None,
                                "response": {
                                    "status_code": 200,
                                    "body": {
                                        "candidates": [
                                            {
                                                "content": {"parts": [{"text": ""}]},
                                                "index": 0,
                                                "finishReason": "STOP",
                                            }
                                        ]
                                    },
                                },
                                "error": None,
                            }
                        )
                        + "\n"
                    )

            return DownloadResult(
                artifact_path=artifact_path,
                content_type="application/jsonl",
                metadata={"provider_job_id": provider_job_id},
            )

        return await asyncio.to_thread(_download)


class GeminiResultParser(ResultParser):
    """Parse Gemini batch JSONL output into a normalized mapping."""

    def __init__(self, results_filename: str = "gemini_batch_results.jsonl") -> None:
        self._results_filename = results_filename

    async def parse(self, ctx: ExecutionTaskContext) -> Mapping[str, Any]:
        results_path = ctx.artifact_dir / self._results_filename
        if not results_path.exists():
            raise ParseError(f"Gemini results file not found at {results_path}")

        records: list[dict[str, Any]] = []
        with results_path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ParseError(f"Malformed JSON in Gemini results: {exc}") from exc
                records.append(payload)

        return {
            "provider": "gemini",
            "request_id": str(ctx.request.id),
            "task_id": str(ctx.task.id),
            "strategy_id": str(ctx.request.strategy_id),
            "prompt": ctx.request.metadata.get("strategy_prompt"),
            "total": len(records),
            "records": records,
        }


def _normalize_model(model: str) -> str:
    model = model.strip()
    if model.startswith("models/"):
        return model
    return f"models/{model}"


def _map_gemini_status(state: str | None) -> str:
    mapping = {
        "JOB_STATE_PENDING": "processing",
        "JOB_STATE_RUNNING": "processing",
        "JOB_STATE_SUCCEEDED": "completed",
        "JOB_STATE_FAILED": "failed",
        "JOB_STATE_CANCELLED": "cancelled",
        "JOB_STATE_EXPIRED": "timeout",
    }
    return mapping.get(state, "processing") if state else "processing"


def _clean_schema_for_gemini(schema: Mapping[str, Any]) -> Mapping[str, Any]:
    """Remove unsupported schema fields for Gemini responseSchema."""

    def _clean(node: object) -> object:
        if isinstance(node, dict):
            cleaned = {
                key: _clean(value)
                for key, value in node.items()
                if key != "additionalProperties"
            }
            return cleaned
        if isinstance(node, list):
            return [_clean(item) for item in node]
        return node

    return _clean(schema)


__all__ = [
    "GeminiBatchExecutor",
    "GeminiProviderConfig",
    "GeminiRequestSerializer",
    "GeminiResultParser",
]
