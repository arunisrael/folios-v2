"""Provider plugin for Anthropic."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from folios_v2.domain import ExecutionMode, ProviderId
from folios_v2.providers import ProviderPlugin, ProviderThrottle, ResultParser
from folios_v2.providers.exceptions import ParseError
from folios_v2.providers.models import ExecutionTaskContext

from .cli_executor import AnthropicCliExecutor
from .direct_executor import AnthropicDirectExecutor


class AnthropicResultParser(ResultParser):
    """Parse Anthropic CLI outputs into structured dictionaries."""

    async def parse(self, ctx: ExecutionTaskContext) -> dict[str, object]:
        """Parse CLI response artifacts, prioritizing structured.json."""
        artifact_dir = ctx.artifact_dir

        # Priority 1: structured.json (extracted JSON payload)
        structured_path = artifact_dir / "structured.json"
        if structured_path.exists():
            try:
                structured: dict[str, Any] = json.loads(structured_path.read_text(encoding="utf-8"))
                return structured
            except json.JSONDecodeError as exc:
                raise ParseError(f"Invalid structured JSON output: {exc}") from exc

        # Priority 2: response.json (full CLI response with metadata)
        response_path = artifact_dir / "response.json"
        if response_path.exists():
            try:
                data: dict[str, Any] = json.loads(response_path.read_text(encoding="utf-8"))
                # If response.json contains a structured field, use that
                if not isinstance(data, dict):
                    raise ParseError(f"response.json is not a dictionary: {type(data)}")
                structured_field = data.get("structured")
                if isinstance(structured_field, dict):
                    return structured_field
                # Otherwise return the full response
                return data
            except json.JSONDecodeError as exc:
                raise ParseError(f"Invalid JSON in response.json: {exc}") from exc

        # Priority 3: Raw stdout if available (legacy fallback)
        if ctx.task.stdout_path:
            stdout_path = Path(ctx.task.stdout_path)
            if stdout_path.exists():
                return {"raw_text": stdout_path.read_text(encoding="utf-8")}

        raise ParseError(
            f"No parseable output found in {artifact_dir} "
            "(expected structured.json or response.json)"
        )


ANTHROPIC_PLUGIN = ProviderPlugin(
    provider_id=ProviderId.ANTHROPIC,
    display_name="Anthropic",
    supports_batch=False,
    supports_cli=True,
    default_mode=ExecutionMode.CLI,
    throttle=ProviderThrottle(max_concurrent=1, requests_per_minute=30),
    serializer=None,
    batch_executor=None,
    cli_executor=AnthropicDirectExecutor(),  # Use direct API instead of CLI
    parser=AnthropicResultParser(),
)

__all__ = ["ANTHROPIC_PLUGIN", "AnthropicCliExecutor", "AnthropicResultParser"]
