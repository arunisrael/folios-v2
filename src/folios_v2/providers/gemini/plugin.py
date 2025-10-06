"""Provider plugin for Gemini."""

from __future__ import annotations

from folios_v2.domain import ExecutionMode, ProviderId
from folios_v2.providers import ProviderPlugin, ProviderThrottle
from folios_v2.providers.exceptions import ProviderError
from folios_v2.providers.local_batch import (
    LocalJSONBatchExecutor,
    LocalJSONParser,
    LocalJSONRequestSerializer,
)

from .batch import GeminiBatchExecutor, GeminiProviderConfig, GeminiRequestSerializer, GeminiResultParser
from .cli_executor import GeminiCliExecutor


def _default_throttle() -> ProviderThrottle:
    return ProviderThrottle(max_concurrent=2, requests_per_minute=40)


def build_gemini_plugin(config: GeminiProviderConfig | None = None) -> ProviderPlugin:
    resolved = config or GeminiProviderConfig.from_env()

    if resolved.api_key:
        serializer = GeminiRequestSerializer(model=resolved.model)
        executor = GeminiBatchExecutor(api_key=resolved.api_key, model=resolved.model)
        parser = GeminiResultParser()
        default_mode = ExecutionMode.BATCH
    else:
        if not resolved.allow_local_fallback:
            raise ProviderError(
                "Gemini API key not configured and local batch fallback disabled",
            )
        serializer = LocalJSONRequestSerializer(ProviderId.GEMINI)
        executor = LocalJSONBatchExecutor(ProviderId.GEMINI)
        parser = LocalJSONParser()
        default_mode = ExecutionMode.BATCH

    return ProviderPlugin(
        provider_id=ProviderId.GEMINI,
        display_name="Gemini",
        supports_batch=True,
        supports_cli=True,
        default_mode=default_mode,
        throttle=_default_throttle(),
        serializer=serializer,
        batch_executor=executor,
        cli_executor=GeminiCliExecutor(),
        parser=parser,
    )


GEMINI_PLUGIN = build_gemini_plugin()

__all__ = ["build_gemini_plugin", "GEMINI_PLUGIN", "GeminiCliExecutor"]
