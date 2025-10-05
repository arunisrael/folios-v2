from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from folios_v2.domain import (
    ExecutionMode,
    ExecutionTask,
    LifecycleState,
    ProviderId,
    Request,
    RequestId,
    RequestPriority,
    RequestType,
    StrategyId,
    TaskId,
)
from folios_v2.providers import (
    BatchExecutor,
    CliExecutor,
    CliResult,
    DownloadResult,
    ExecutionTaskContext,
    ProviderPlugin,
    ProviderThrottle,
    RequestSerializer,
    ResultParser,
    SerializeResult,
    SubmitResult,
)
from folios_v2.providers.models import PollResult
from folios_v2.runtime import BatchRuntime, CliRuntime


class DummySerializer(RequestSerializer):
    async def serialize(self, ctx: ExecutionTaskContext) -> SerializeResult:
        return SerializeResult(
            payload_path=ctx.artifact_dir / "payload.json",
            content_type="application/json",
        )


class DummyBatchExecutor(BatchExecutor):
    async def submit(self, ctx: ExecutionTaskContext, payload: SerializeResult) -> SubmitResult:  # type: ignore[override]
        return SubmitResult(provider_job_id="job-123")

    async def poll(
        self,
        ctx: ExecutionTaskContext,
        provider_job_id: str,
    ) -> PollResult:  # type: ignore[override]
        return PollResult(completed=True, status="succeeded")

    async def download(self, ctx: ExecutionTaskContext, provider_job_id: str) -> DownloadResult:  # type: ignore[override]
        return DownloadResult(
            artifact_path=ctx.artifact_dir / "result.json",
            content_type="application/json",
        )


class DummyCliExecutor(CliExecutor):
    async def run(
        self,
        ctx: ExecutionTaskContext,
        payload: SerializeResult | None = None,
    ) -> CliResult:  # type: ignore[override]
        return CliResult(exit_code=0, stdout_path=None, stderr_path=None)


class DummyParser(ResultParser):
    async def parse(self, ctx: ExecutionTaskContext) -> dict[str, str]:  # type: ignore[override]
        return {"status": "ok"}


def _build_context(tmp_path: Path) -> ExecutionTaskContext:
    request = Request(
        id=RequestId(uuid4()),
        strategy_id=StrategyId(uuid4()),
        provider_id=ProviderId.OPENAI,
        mode=ExecutionMode.BATCH,
        request_type=RequestType.RESEARCH,
        priority=RequestPriority.NORMAL,
    )
    task = ExecutionTask(
        id=TaskId(uuid4()),
        request_id=request.id,
        sequence=1,
        mode=ExecutionMode.BATCH,
        lifecycle_state=LifecycleState.PENDING,
    )
    artifact_dir = tmp_path / str(request.id)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    return ExecutionTaskContext(request=request, task=task, artifact_dir=artifact_dir)


def test_batch_runtime_executes(tmp_path: Path) -> None:
    ctx = _build_context(tmp_path)
    plugin = ProviderPlugin(
        provider_id=ProviderId.OPENAI,
        display_name="Dummy",
        supports_batch=True,
        supports_cli=False,
        default_mode=ExecutionMode.BATCH,
        throttle=ProviderThrottle(max_concurrent=1),
        serializer=DummySerializer(),
        parser=DummyParser(),
        batch_executor=DummyBatchExecutor(),
    )
    runtime = BatchRuntime(poll_interval_seconds=0.01, max_polls=3)
    outcome = asyncio.run(runtime.run(plugin, ctx))
    assert outcome.submit_result.provider_job_id == "job-123"
    assert outcome.download_result.content_type == "application/json"


def test_cli_runtime_executes(tmp_path: Path) -> None:
    ctx = _build_context(tmp_path)
    plugin = ProviderPlugin(
        provider_id=ProviderId.OPENAI,
        display_name="Dummy",
        supports_batch=False,
        supports_cli=True,
        default_mode=ExecutionMode.CLI,
        throttle=ProviderThrottle(max_concurrent=1),
        serializer=DummySerializer(),
        parser=DummyParser(),
        cli_executor=DummyCliExecutor(),
    )
    runtime = CliRuntime()
    outcome = asyncio.run(runtime.run(plugin, ctx))
    assert outcome.result.exit_code == 0
