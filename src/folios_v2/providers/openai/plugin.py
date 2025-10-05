"""Provider plugin for OpenAI."""

from __future__ import annotations

from folios_v2.domain import ExecutionMode, ProviderId
from folios_v2.providers import ProviderPlugin, ProviderThrottle
from folios_v2.providers.local_batch import (
    LocalJSONBatchExecutor,
    LocalJSONParser,
    LocalJSONRequestSerializer,
)

from .cli_executor import CodexCliExecutor

OPENAI_PLUGIN = ProviderPlugin(
    provider_id=ProviderId.OPENAI,
    display_name="OpenAI",
    supports_batch=True,
    supports_cli=True,
    default_mode=ExecutionMode.CLI,
    throttle=ProviderThrottle(max_concurrent=2, requests_per_minute=60),
    serializer=LocalJSONRequestSerializer(ProviderId.OPENAI),
    batch_executor=LocalJSONBatchExecutor(ProviderId.OPENAI),
    cli_executor=CodexCliExecutor(),
    parser=LocalJSONParser(),
)

__all__ = ["OPENAI_PLUGIN", "CodexCliExecutor"]
