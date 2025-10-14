"""Direct Anthropic API executor - bypasses CLI and calls API directly."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from folios_v2.providers import CliExecutor, CliResult, ExecutionTaskContext, SerializeResult
from folios_v2.providers.exceptions import ExecutionError


@dataclass(slots=True)
class AnthropicDirectExecutor(CliExecutor):
    """Execute Anthropic research by calling the API directly via Python SDK."""

    model: str = "claude-sonnet-4-5-20250929"

    async def run(
        self,
        ctx: ExecutionTaskContext,
        payload: SerializeResult | None = None,
    ) -> CliResult:
        """Execute via Anthropic API directly."""
        _ = payload
        prompt = ctx.request.metadata.get("strategy_prompt")
        if not prompt:
            msg = "Strategy prompt missing from request metadata"
            raise ExecutionError(msg)

        artifact_dir = ctx.artifact_dir
        artifact_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = artifact_dir / "prompt.txt"
        prompt_path.write_text(prompt, encoding="utf-8")

        # Get API key from environment
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ExecutionError("ANTHROPIC_API_KEY not found in environment")

        try:
            # Import Anthropic SDK
            from anthropic import Anthropic
        except ImportError as e:
            raise ExecutionError(
                "anthropic package not installed. Install with: pip install anthropic"
            ) from e

        # Create client
        client = Anthropic(api_key=api_key)

        # Prepare response payload
        response_payload: dict[str, Any] = {
            "provider": "anthropic",
            "prompt": prompt,
            "model": self.model,
            "method": "direct_api",
        }

        try:
            # Call the API
            message = client.messages.create(
                model=self.model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract response text
            result_text = ""
            for block in message.content:
                if hasattr(block, "text"):
                    result_text += block.text

            response_payload["message_id"] = message.id
            response_payload["result"] = result_text
            response_payload["usage"] = {
                "input_tokens": message.usage.input_tokens,
                "output_tokens": message.usage.output_tokens,
            }
            response_payload["stop_reason"] = message.stop_reason

            # Try to parse structured JSON from result
            structured_payload: dict[str, Any] | None = None
            try:
                # First try: parse as direct JSON
                decoded = json.loads(result_text)
                if isinstance(decoded, dict):
                    structured_payload = decoded
            except json.JSONDecodeError:
                # Second try: extract from markdown blocks
                structured_payload = _extract_structured_json(result_text)

            if structured_payload is not None:
                response_payload["structured"] = structured_payload

            exit_code = 0

        except Exception as e:
            response_payload["error"] = str(e)
            response_payload["error_type"] = type(e).__name__
            result_text = f"Error: {e!s}"
            exit_code = 1

        response_payload["exit_code"] = exit_code

        # Save response
        response_path = artifact_dir / "response.json"
        response_path.write_text(
            json.dumps(response_payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        # Save structured payload if available
        structured_path: Path | None = None
        if "structured" in response_payload:
            structured_path = artifact_dir / "structured.json"
            structured_path.write_text(
                json.dumps(response_payload["structured"], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        return CliResult(
            exit_code=exit_code,
            stdout_path=None,
            stderr_path=None,
            metadata={
                "method": "direct_api",
                "model": self.model,
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


__all__ = ["AnthropicDirectExecutor"]
