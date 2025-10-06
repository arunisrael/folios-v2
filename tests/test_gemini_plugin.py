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
from folios_v2.providers.gemini import (
    GeminiProviderConfig,
    GeminiRequestSerializer,
    build_gemini_plugin,
)
from folios_v2.providers.models import ExecutionTaskContext


def test_build_gemini_plugin_requires_key_when_fallback_disabled() -> None:
    cfg = GeminiProviderConfig(api_key=None, allow_local_fallback=False)
    with pytest.raises(ProviderError):
        build_gemini_plugin(cfg)


def test_gemini_serializer_includes_schema(tmp_path: Path) -> None:
    plugin = build_gemini_plugin(
        GeminiProviderConfig(api_key="fake-key", allow_local_fallback=True)
    )
    assert isinstance(plugin.serializer, GeminiRequestSerializer)

    request = Request(
        id=uuid4(),
        strategy_id=uuid4(),
        provider_id=ProviderId.GEMINI,
        mode=ExecutionMode.BATCH,
        request_type=RequestType.RESEARCH,
        priority=RequestPriority.NORMAL,
        lifecycle_state=LifecycleState.PENDING,
        metadata={"strategy_prompt": "Focus on resilient consumer staples with upside catalysts."},
    )
    task = ExecutionTask(
        id=uuid4(),
        request_id=request.id,
        sequence=1,
        mode=ExecutionMode.BATCH,
        lifecycle_state=LifecycleState.PENDING,
    )
    ctx = ExecutionTaskContext(request=request, task=task, artifact_dir=tmp_path / "gemini")

    serialize_result = asyncio.run(plugin.serializer.serialize(ctx))
    payload = json.loads(Path(serialize_result.payload_path).read_text())

    assert payload["requests"][0]["custom_id"] == str(task.id)
    gen_config = payload["requests"][0]["payload"]["generationConfig"]
    assert gen_config["responseMimeType"] == "application/json"
    assert "responseSchema" in gen_config

    text = payload["requests"][0]["payload"]["contents"][0]["parts"][0]["text"]
    assert "Return only valid JSON" in text
