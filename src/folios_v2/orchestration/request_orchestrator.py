"""Request orchestration service."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime
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
    Strategy,
    TaskId,
)
from folios_v2.persistence import UnitOfWork
from folios_v2.providers import ProviderRegistry
from folios_v2.utils import ensure_utc

from .prompt_builder import build_research_prompt

UnitOfWorkFactory = Callable[[], UnitOfWork]


class RequestOrchestrator:
    """Creates provider-bound requests and bootstraps execution tasks."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        registry: ProviderRegistry,
        artifacts_root: Path,
    ) -> None:
        self._uow_factory = uow_factory
        self._registry = registry
        self._artifacts_root = artifacts_root

    async def enqueue_request(
        self,
        strategy: Strategy,
        *,
        provider_id: ProviderId,
        request_type: RequestType,
        mode: ExecutionMode,
        priority: RequestPriority = RequestPriority.NORMAL,
        scheduled_for: datetime | None = None,
        metadata: Mapping[str, str] | None = None,
    ) -> tuple[Request, ExecutionTask]:
        self._registry.require(provider_id, mode)
        request_id = RequestId(uuid4())
        task_id = TaskId(uuid4())
        scheduled_ts = ensure_utc(scheduled_for) if scheduled_for else None

        prompt = build_research_prompt(strategy, mode=mode)

        base_metadata = {
            "strategy_name": strategy.name,
            "provider": provider_id.value,
            "request_type": request_type.value,
            "strategy_prompt": prompt,
            "output_schema": "investment_analysis_v1",
        }
        if metadata is not None:
            base_metadata.update(metadata)

        request = Request(
            id=request_id,
            strategy_id=strategy.id,
            provider_id=provider_id,
            mode=mode,
            request_type=request_type,
            priority=priority,
            lifecycle_state=LifecycleState.PENDING,
            metadata=base_metadata,
            scheduled_for=scheduled_ts,
        )

        artifacts_dir = self._artifacts_root / str(request_id) / str(task_id)
        task = ExecutionTask(
            id=task_id,
            request_id=request_id,
            sequence=1,
            mode=mode,
            lifecycle_state=LifecycleState.PENDING,
            metadata={"artifact_dir": str(artifacts_dir)},
        )

        async with self._uow_factory() as uow:
            await uow.request_repository.add(request)
            await uow.task_repository.add(task)
            await uow.commit()

        return request, task


__all__ = ["RequestOrchestrator"]
