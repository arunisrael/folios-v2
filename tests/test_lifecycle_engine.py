from __future__ import annotations

import asyncio
from uuid import uuid4

from folios_v2.domain import (
    ExecutionMode,
    ExecutionTask,
    LifecycleState,
    ProviderId,
    Request,
    RequestPriority,
    RequestType,
)
from folios_v2.orchestration import LifecycleEngine
from folios_v2.persistence import InMemoryUnitOfWork

_SHARED_UOW = InMemoryUnitOfWork()


def _factory() -> InMemoryUnitOfWork:
    return _SHARED_UOW


async def _seed() -> tuple[Request, ExecutionTask]:
    request = Request(
        id=uuid4(),
        strategy_id=uuid4(),
        provider_id=ProviderId.OPENAI,
        mode=ExecutionMode.CLI,
        request_type=RequestType.RESEARCH,
        priority=RequestPriority.NORMAL,
        lifecycle_state=LifecycleState.PENDING,
        metadata={"strategy_prompt": "example"},
    )
    task = ExecutionTask(
        id=uuid4(),
        request_id=request.id,
        sequence=1,
        mode=ExecutionMode.CLI,
        lifecycle_state=LifecycleState.PENDING,
    )
    async with _factory() as uow:
        await uow.request_repository.add(request)
        await uow.task_repository.add(task)
        await uow.commit()
    return request, task


def test_lifecycle_engine_transitions_request_and_task() -> None:
    request, task = asyncio.run(_seed())
    engine = LifecycleEngine(_factory)

    updated_request = asyncio.run(
        engine.transition_request(
            request.id,
            next_state=LifecycleState.SCHEDULED,
            expected_states=(LifecycleState.PENDING,),
            attributes={"reason": "test"},
        )
    )
    assert updated_request.lifecycle_state is LifecycleState.SCHEDULED

    updated_task = asyncio.run(
        engine.transition_task(
            task.id,
            next_state=LifecycleState.SUCCEEDED,
            expected_states=(LifecycleState.PENDING,),
            attributes={"note": "finished"},
        )
    )
    assert updated_task.lifecycle_state is LifecycleState.SUCCEEDED

    async def _load_logs() -> int:
        async with _factory() as uow:
            logs = await uow.log_repository.list_for_request(request.id)
            return len(logs)

    assert asyncio.run(_load_logs()) == 2
