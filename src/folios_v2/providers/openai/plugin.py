"""Provider plugin for OpenAI."""

from __future__ import annotations

from folios_v2.domain import ExecutionMode, ProviderId
from folios_v2.providers import ProviderPlugin, ProviderThrottle
from folios_v2.providers.exceptions import ProviderError
from folios_v2.providers.local_batch import (
    LocalJSONBatchExecutor,
    LocalJSONParser,
    LocalJSONRequestSerializer,
)

from .batch import (
    OpenAIBatchExecutor,
    OpenAIProviderConfig,
    OpenAIRequestSerializer,
    OpenAIResultParser,
)
from .cli_executor import CodexCliExecutor


def _default_throttle() -> ProviderThrottle:
    return ProviderThrottle(max_concurrent=2, requests_per_minute=60)


def build_openai_plugin(config: OpenAIProviderConfig | None = None) -> ProviderPlugin:
    """Construct an OpenAI provider plugin using real batch execution when configured."""

    resolved_config = config or OpenAIProviderConfig.from_env()

    default_mode = ExecutionMode.BATCH

    if resolved_config.api_key:
        serializer = OpenAIRequestSerializer(
            model=resolved_config.model,
            system_message=resolved_config.system_message,
        )
        executor = OpenAIBatchExecutor(
            api_key=resolved_config.api_key,
            endpoint=resolved_config.endpoint,
            completion_window=resolved_config.completion_window,
        )
        parser = OpenAIResultParser()
    else:
        if not resolved_config.allow_local_fallback:
            raise ProviderError(
                "OpenAI API key not configured and local batch fallback disabled",
            )
        serializer = LocalJSONRequestSerializer(ProviderId.OPENAI)
        executor = LocalJSONBatchExecutor(ProviderId.OPENAI)
        parser = LocalJSONParser()

    return ProviderPlugin(
        provider_id=ProviderId.OPENAI,
        display_name="OpenAI",
        supports_batch=True,
        supports_cli=True,
        default_mode=default_mode,
        throttle=_default_throttle(),
        serializer=serializer,
        batch_executor=executor,
        cli_executor=CodexCliExecutor(),
        parser=parser,
    )


OPENAI_PLUGIN = build_openai_plugin()

__all__ = [
    "OPENAI_PLUGIN",
    "CodexCliExecutor",
    "build_openai_plugin",
]
