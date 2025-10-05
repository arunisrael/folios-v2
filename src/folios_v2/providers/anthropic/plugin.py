"""Provider plugin for Anthropic."""

from __future__ import annotations

from folios_v2.domain import ExecutionMode, ProviderId
from folios_v2.providers import ProviderPlugin, ProviderThrottle
from folios_v2.providers.local_batch import (
    LocalJSONBatchExecutor,
    LocalJSONParser,
    LocalJSONRequestSerializer,
)

from .cli_executor import AnthropicCliExecutor

ANTHROPIC_PLUGIN = ProviderPlugin(
    provider_id=ProviderId.ANTHROPIC,
    display_name="Anthropic",
    supports_batch=True,
    supports_cli=True,
    default_mode=ExecutionMode.CLI,
    throttle=ProviderThrottle(max_concurrent=1, requests_per_minute=30),
    serializer=LocalJSONRequestSerializer(ProviderId.ANTHROPIC),
    batch_executor=LocalJSONBatchExecutor(ProviderId.ANTHROPIC),
    cli_executor=AnthropicCliExecutor(),
    parser=LocalJSONParser(),
)

__all__ = ["ANTHROPIC_PLUGIN", "AnthropicCliExecutor"]
