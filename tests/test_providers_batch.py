from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

import pytest

from folios_v2.domain import (
    ExecutionMode,
    ExecutionTask,
    LifecycleState,
    Request,
    RequestPriority,
    RequestType,
)
from folios_v2.providers import ProviderPlugin
from folios_v2.providers.anthropic import ANTHROPIC_PLUGIN
from folios_v2.providers.gemini import build_gemini_plugin
from folios_v2.providers.gemini.batch import GeminiProviderConfig
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.providers.openai import build_openai_plugin
from folios_v2.providers.openai.batch import OpenAIProviderConfig
from folios_v2.runtime import BatchRuntime

LOCAL_OPENAI_PLUGIN = build_openai_plugin(
    OpenAIProviderConfig(api_key=None, allow_local_fallback=True)
)
LOCAL_GEMINI_PLUGIN = build_gemini_plugin(
    GeminiProviderConfig(api_key=None, allow_local_fallback=True)
)


@pytest.mark.parametrize(
    "plugin",
    [LOCAL_OPENAI_PLUGIN, LOCAL_GEMINI_PLUGIN, ANTHROPIC_PLUGIN],
)
def test_local_batch_execution(tmp_path: Path, plugin: ProviderPlugin) -> None:
    # Skip test if plugin doesn't support batch mode
    if not plugin.supports_batch:
        pytest.skip(f"{plugin.display_name} does not support batch mode")

    strategy_id = uuid4()
    request = Request(
        id=uuid4(),
        strategy_id=strategy_id,
        provider_id=plugin.provider_id,
        mode=ExecutionMode.BATCH,
        request_type=RequestType.RESEARCH,
        priority=RequestPriority.NORMAL,
        lifecycle_state=LifecycleState.PENDING,
        metadata={"strategy_prompt": "Explain quantum tunneling"},
    )
    task = ExecutionTask(
        id=uuid4(),
        request_id=request.id,
        sequence=1,
        mode=ExecutionMode.BATCH,
        lifecycle_state=LifecycleState.PENDING,
    )
    ctx = ExecutionTaskContext(
        request=request,
        task=task,
        artifact_dir=tmp_path / plugin.provider_id.value,
    )

    runtime = BatchRuntime(poll_interval_seconds=0.01, max_polls=10)

    async def _run() -> None:
        payload = await plugin.serializer.serialize(ctx) if plugin.serializer else None
        if payload is None:
            pytest.fail("Batch serializer is required for local batch execution")
        await runtime.run(plugin, ctx)

    asyncio.run(_run())

    parsed = asyncio.run(plugin.parser.parse(ctx))
    assert parsed.get("provider") == plugin.provider_id.value
    assert parsed.get("prompt") == "Explain quantum tunneling"
    assert parsed.get("strategy_id") == str(strategy_id)
