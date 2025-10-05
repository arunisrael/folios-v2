"""Provider plugin for Gemini."""

from __future__ import annotations

from folios_v2.domain import ExecutionMode, ProviderId
from folios_v2.providers import ProviderPlugin, ProviderThrottle
from folios_v2.providers.local_batch import (
    LocalJSONBatchExecutor,
    LocalJSONParser,
    LocalJSONRequestSerializer,
)

from .cli_executor import GeminiCliExecutor

GEMINI_PLUGIN = ProviderPlugin(
    provider_id=ProviderId.GEMINI,
    display_name="Gemini",
    supports_batch=True,
    supports_cli=True,
    default_mode=ExecutionMode.CLI,
    throttle=ProviderThrottle(max_concurrent=2, requests_per_minute=40),
    serializer=LocalJSONRequestSerializer(ProviderId.GEMINI),
    batch_executor=LocalJSONBatchExecutor(ProviderId.GEMINI),
    cli_executor=GeminiCliExecutor(),
    parser=LocalJSONParser(),
)

__all__ = ["GEMINI_PLUGIN", "GeminiCliExecutor"]
