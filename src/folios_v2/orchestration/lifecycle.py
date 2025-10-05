"""Lifecycle engine handling request/task state transitions."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from folios_v2.domain import (
    ExecutionTask,
    LifecycleState,
    Request,
    RequestId,
    RequestLogEntry,
    TaskId,
)
from folios_v2.persistence import NotFoundError, UnitOfWork
from folios_v2.utils import utc_now

from .exceptions import InvalidTransitionError

UnitOfWorkFactory = Callable[[], UnitOfWork]


class LifecycleEngine:
    """Orchestrates transitions for requests and tasks with logging."""

    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def transition_request(
        self,
        request_id: RequestId,
        *,
        next_state: LifecycleState,
        expected_states: tuple[LifecycleState, ...] | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> Request:
        async with self._uow_factory() as uow:
            request = await uow.request_repository.get(request_id)
            if request is None:
                msg = f"Request {request_id} not found"
                raise NotFoundError(msg)
            if expected_states is not None and request.lifecycle_state not in expected_states:
                msg = (
                    f"Cannot transition request {request_id} from {request.lifecycle_state} "
                    f"to {next_state}; expected {expected_states}"
                )
                raise InvalidTransitionError(msg)

            updated = request.model_copy(
                update={
                    "lifecycle_state": next_state,
                    "updated_at": utc_now(),
                }
            )
            await uow.request_repository.update(updated)
            await uow.log_repository.add(
                RequestLogEntry(
                    request_id=request_id,
                    task_id=None,
                    previous_state=request.lifecycle_state,
                    next_state=next_state,
                    attributes=dict(attributes or {}),
                ).model_dump()
            )
            await uow.commit()
            return updated

    async def transition_task(
        self,
        task_id: TaskId,
        *,
        next_state: LifecycleState,
        expected_states: tuple[LifecycleState, ...] | None = None,
        attributes: Mapping[str, str] | None = None,
    ) -> ExecutionTask:
        async with self._uow_factory() as uow:
            task = await uow.task_repository.get(task_id)
            if task is None:
                msg = f"Task {task_id} not found"
                raise NotFoundError(msg)
            if expected_states is not None and task.lifecycle_state not in expected_states:
                msg = (
                    f"Cannot transition task {task_id} from {task.lifecycle_state} "
                    f"to {next_state}; expected {expected_states}"
                )
                raise InvalidTransitionError(msg)

            updated = task.model_copy(
                update={
                    "lifecycle_state": next_state,
                    "updated_at": utc_now(),
                }
            )
            await uow.task_repository.update(updated)
            await uow.log_repository.add(
                RequestLogEntry(
                    request_id=updated.request_id,
                    task_id=task_id,
                    previous_state=task.lifecycle_state,
                    next_state=next_state,
                    attributes=dict(attributes or {}),
                ).model_dump()
            )
            await uow.commit()
            return updated


__all__ = ["LifecycleEngine", "UnitOfWorkFactory"]
