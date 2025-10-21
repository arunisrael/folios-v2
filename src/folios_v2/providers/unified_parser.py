"""Unified result parser that handles both batch and CLI execution outputs."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from folios_v2.providers import ExecutionTaskContext, ResultParser
from folios_v2.providers.exceptions import ParseError


class UnifiedResultParser(ResultParser):
    """
    Parser that intelligently detects and parses both batch and CLI outputs.

    For CLI mode, looks for:
    - structured.json (preferred)
    - response.json (fallback)

    For batch mode, looks for provider-specific batch result files:
    - gemini_batch_results.jsonl
    - openai_batch_results.jsonl
    - anthropic_batch_results.jsonl
    """

    def __init__(self, provider_id: str) -> None:
        self.provider_id = provider_id

    async def parse(self, ctx: ExecutionTaskContext) -> Mapping[str, Any]:
        artifact_dir = ctx.artifact_dir

        # Try CLI-style outputs first (most common for new executions)
        structured_path = artifact_dir / "structured.json"
        if structured_path.exists():
            return await self._parse_cli_structured(ctx, structured_path)

        response_path = artifact_dir / "response.json"
        if response_path.exists():
            return await self._parse_cli_response(ctx, response_path)

        # Try batch-style outputs
        batch_path = artifact_dir / f"{self.provider_id}_batch_results.jsonl"
        if batch_path.exists():
            return await self._parse_batch_jsonl(ctx, batch_path)

        # No recognizable output found
        available_files = list(artifact_dir.glob("*"))
        raise ParseError(
            f"No parseable results found in {artifact_dir}. "
            f"Available files: {[f.name for f in available_files]}"
        )

    async def _parse_cli_structured(
        self, ctx: ExecutionTaskContext, structured_path: Path
    ) -> Mapping[str, Any]:
        """Parse CLI structured.json output (already contains recommendations)."""
        try:
            data = json.loads(structured_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ParseError(f"Malformed JSON in {structured_path}: {exc}") from exc

        # Ensure we have the recommendations field
        if not isinstance(data, dict):
            raise ParseError(f"Expected dict in {structured_path}, got {type(data)}")

        return {
            "provider": self.provider_id,
            "request_id": str(ctx.request.id),
            "task_id": str(ctx.task.id),
            "strategy_id": str(ctx.request.strategy_id),
            "prompt": ctx.request.metadata.get("strategy_prompt"),
            "source": "cli_structured",
            **data,  # Include all fields from structured.json
        }

    async def _parse_cli_response(
        self, ctx: ExecutionTaskContext, response_path: Path
    ) -> Mapping[str, Any]:
        """Parse CLI response.json output (may need to extract structured data)."""
        try:
            data = json.loads(response_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ParseError(f"Malformed JSON in {response_path}: {exc}") from exc

        if not isinstance(data, dict):
            raise ParseError(f"Expected dict in {response_path}, got {type(data)}")

        # Check if structured data is embedded
        if "structured" in data and isinstance(data["structured"], dict):
            structured = data["structured"]
            return {
                "provider": self.provider_id,
                "request_id": str(ctx.request.id),
                "task_id": str(ctx.task.id),
                "strategy_id": str(ctx.request.strategy_id),
                "prompt": ctx.request.metadata.get("strategy_prompt"),
                "source": "cli_response_structured",
                **structured,
            }

        # Fallback: treat entire response as recommendations container
        recommendations = data.get("recommendations", [])
        return {
            "provider": self.provider_id,
            "request_id": str(ctx.request.id),
            "task_id": str(ctx.task.id),
            "strategy_id": str(ctx.request.strategy_id),
            "prompt": ctx.request.metadata.get("strategy_prompt"),
            "source": "cli_response_raw",
            "recommendations": recommendations,
            "raw_data": data,
        }

    async def _parse_batch_jsonl(
        self, ctx: ExecutionTaskContext, batch_path: Path
    ) -> Mapping[str, Any]:
        """Parse batch JSONL output."""
        records: list[dict[str, Any]] = []
        with batch_path.open(encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    payload = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ParseError(f"Malformed JSON in batch results: {exc}") from exc
                records.append(payload)

        # Extract recommendations from batch records
        # Batch format varies by provider, so we try common patterns
        recommendations: list[dict[str, Any]] = []

        def _extend_from_payload(payload: object) -> None:
            """Normalize provider payloads into recommendations lists."""

            if payload is None:
                return

            if isinstance(payload, str):
                try:
                    decoded = json.loads(payload)
                except json.JSONDecodeError:
                    return
                else:
                    _extend_from_payload(decoded)
                    return

            if isinstance(payload, list):
                for item in payload:
                    _extend_from_payload(item)
                return

            if not isinstance(payload, Mapping):
                return

            recs = payload.get("recommendations")
            if isinstance(recs, list):
                recommendations.extend(r for r in recs if isinstance(r, Mapping))

            # Some OpenAI responses wrap fields under a "properties" object.
            properties = payload.get("properties")
            if isinstance(properties, Mapping):
                recs_from_properties = properties.get("recommendations")
                if isinstance(recs_from_properties, list):
                    recommendations.extend(
                        r for r in recs_from_properties if isinstance(r, Mapping)
                    )

            # Allow providers to nest additional structured payloads.
            for key in ("data", "result", "output"):
                nested = payload.get(key)
                if nested:
                    _extend_from_payload(nested)

            # Gemini batch responses often expose a "content" dictionary with
            # parts that already contain recommendation objects.
            content = payload.get("content")
            if isinstance(content, Mapping):
                _extend_from_payload(content)

            parts = payload.get("parts")
            if isinstance(parts, list):
                text_chunks: list[str] = []
                for part in parts:
                    if isinstance(part, Mapping):
                        text = part.get("text")
                        if isinstance(text, str):
                            text_chunks.append(text)
                if text_chunks:
                    _extend_from_payload("".join(text_chunks))

        for record in records:
            if not isinstance(record, dict):
                continue

            # Try direct recommendations field
            if "recommendations" in record:
                _extend_from_payload(record)
                continue

            response = record.get("response")
            if not isinstance(response, dict):
                continue

            # Legacy Anthrop ic/OpenAI simulator format: response.text holds JSON string
            if "text" in response and isinstance(response["text"], str):
                try:
                    text_data = json.loads(response["text"])
                except json.JSONDecodeError:
                    text_data = None
                _extend_from_payload(text_data)
                continue

            # Real OpenAI batch responses embed the chat body under response.body
            body = response.get("body")
            if isinstance(body, dict):
                choices = body.get("choices")
                if isinstance(choices, list):
                    for choice in choices:
                        if not isinstance(choice, dict):
                            continue
                        message = choice.get("message")
                        if not isinstance(message, dict):
                            continue
                        content = message.get("content")
                        if isinstance(content, str):
                            try:
                                parsed_content = json.loads(content)
                            except json.JSONDecodeError:
                                continue
                            _extend_from_payload(parsed_content)
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, Mapping):
                                    text = block.get("text")
                                    if isinstance(text, str):
                                        _extend_from_payload(text)

                candidates = body.get("candidates")
                if isinstance(candidates, list):
                    for candidate in candidates:
                        if not isinstance(candidate, Mapping):
                            continue
                        cand_content = candidate.get("content")
                        if isinstance(cand_content, Mapping):
                            _extend_from_payload(cand_content)

        return {
            "provider": self.provider_id,
            "request_id": str(ctx.request.id),
            "task_id": str(ctx.task.id),
            "strategy_id": str(ctx.request.strategy_id),
            "prompt": ctx.request.metadata.get("strategy_prompt"),
            "source": "batch_jsonl",
            "total": len(records),
            "records": records,
            "recommendations": recommendations,
        }


__all__ = ["UnifiedResultParser"]
