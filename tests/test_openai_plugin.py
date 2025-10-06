from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import pytest

from folios_v2.domain import (
    ExecutionMode,
    ExecutionTask,
    LifecycleState,
    ProviderId,
    Request,
    RequestPriority,
    RequestType,
)
from folios_v2.providers.exceptions import ProviderError
from folios_v2.providers.models import ExecutionTaskContext
from folios_v2.providers.openai import (
    OpenAIBatchExecutor,
    OpenAIProviderConfig,
    OpenAIRequestSerializer,
    OpenAIResultParser,
    build_openai_plugin,
)


def test_build_openai_plugin_uses_real_components_when_api_key_present() -> None:
    plugin = build_openai_plugin(
        OpenAIProviderConfig(
            api_key="test-key",
            allow_local_fallback=True,
        )
    )

    assert isinstance(plugin.serializer, OpenAIRequestSerializer)
    assert isinstance(plugin.batch_executor, OpenAIBatchExecutor)
    assert isinstance(plugin.parser, OpenAIResultParser)


def test_build_openai_plugin_requires_key_when_fallback_disabled() -> None:
    cfg = OpenAIProviderConfig(api_key=None, allow_local_fallback=False)
    with pytest.raises(ProviderError):
        build_openai_plugin(cfg)


def test_openai_serializer_includes_investment_schema(tmp_path: Path) -> None:
    plugin = build_openai_plugin(
        OpenAIProviderConfig(api_key="test-key", allow_local_fallback=True)
    )
    assert isinstance(plugin.serializer, OpenAIRequestSerializer)

    request = Request(
        id=uuid4(),
        strategy_id=uuid4(),
        provider_id=ProviderId.OPENAI,
        mode=ExecutionMode.BATCH,
        request_type=RequestType.RESEARCH,
        priority=RequestPriority.NORMAL,
        lifecycle_state=LifecycleState.PENDING,
        metadata={"strategy_prompt": "Focus on energy transition plays"},
    )
    task = ExecutionTask(
        id=uuid4(),
        request_id=request.id,
        sequence=1,
        mode=ExecutionMode.BATCH,
        lifecycle_state=LifecycleState.PENDING,
    )
    ctx = ExecutionTaskContext(request=request, task=task, artifact_dir=tmp_path / "openai")

    result = asyncio.run(plugin.serializer.serialize(ctx))
    payload = json.loads(Path(result.payload_path).read_text())

    assert payload["custom_id"] == str(task.id)
    schema = payload["body"]["response_format"]["json_schema"]
    assert schema["name"] == "investment_analysis"
    assert "recommendations" in schema["schema"]["properties"]
