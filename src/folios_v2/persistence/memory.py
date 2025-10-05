"""In-memory repository implementations for unit testing."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, TypeVar

from folios_v2.domain import (
    EmailDigest,
    ExecutionTask,
    Order,
    PortfolioAccount,
    Position,
    PositionSnapshot,
    Request,
    Strategy,
    StrategyRun,
    StrategySchedule,
    StrategyStatus,
)
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.types import (
    DigestId,
    OrderId,
    PositionId,
    PositionSnapshotId,
    RequestId,
    RunId,
    StrategyId,
    TaskId,
)
from folios_v2.persistence.interfaces import (
    EmailDigestRepository,
    ExecutionTaskRepository,
    OrderRepository,
    PortfolioAccountRepository,
    PositionRepository,
    PositionSnapshotRepository,
    RequestLogRepository,
    RequestRepository,
    StrategyRepository,
    StrategyRunRepository,
    StrategyScheduleRepository,
    UnitOfWork,
)

T = TypeVar("T")


def _copy(value: T) -> T:
    return deepcopy(value)


@dataclass
class InMemoryStrategyRepository(StrategyRepository):
    _strategies: dict[StrategyId, Strategy] = field(default_factory=dict)

    async def get(self, strategy_id: StrategyId) -> Strategy | None:
        return _copy(self._strategies.get(strategy_id))

    async def list_active(self) -> Sequence[Strategy]:
        return [
            _copy(strategy)
            for strategy in self._strategies.values()
            if strategy.status == StrategyStatus.ACTIVE
        ]

    async def upsert(self, strategy: Strategy) -> None:
        self._strategies[strategy.id] = strategy

    async def delete(self, strategy_id: StrategyId) -> None:
        self._strategies.pop(strategy_id, None)


@dataclass
class InMemoryStrategyScheduleRepository(StrategyScheduleRepository):
    _schedules: dict[StrategyId, StrategySchedule] = field(default_factory=dict)

    async def get(self, strategy_id: StrategyId) -> StrategySchedule | None:
        return _copy(self._schedules.get(strategy_id))

    async def upsert(self, schedule: StrategySchedule) -> None:
        self._schedules[schedule.strategy_id] = schedule

    async def list_all(self) -> Sequence[StrategySchedule]:
        return [_copy(schedule) for schedule in self._schedules.values()]


@dataclass
class InMemoryStrategyRunRepository(StrategyRunRepository):
    _runs: dict[RunId, StrategyRun] = field(default_factory=dict)

    async def get(self, run_id: RunId) -> StrategyRun | None:
        return _copy(self._runs.get(run_id))

    async def find_by_strategy_week(
        self,
        strategy_id: StrategyId,
        iso_week: tuple[int, int],
    ) -> StrategyRun | None:
        for run in self._runs.values():
            if run.strategy_id == strategy_id and run.iso_week == iso_week:
                return _copy(run)
        return None

    async def add(self, run: StrategyRun) -> None:
        self._runs[run.id] = run

    async def update(self, run: StrategyRun) -> None:
        self._runs[run.id] = run


@dataclass
class InMemoryRequestRepository(RequestRepository):
    _requests: dict[RequestId, Request] = field(default_factory=dict)

    async def get(self, request_id: RequestId) -> Request | None:
        return _copy(self._requests.get(request_id))

    async def add(self, request: Request) -> None:
        self._requests[request.id] = request

    async def update(self, request: Request) -> None:
        if request.id not in self._requests:
            msg = f"Request {request.id} not found"
            raise KeyError(msg)
        self._requests[request.id] = request

    async def list_pending(self, *, limit: int) -> Sequence[Request]:
        pending = [
            req
            for req in self._requests.values()
            if req.lifecycle_state
            in {req.lifecycle_state.PENDING, req.lifecycle_state.SCHEDULED}
        ]
        sorted_requests = sorted(pending, key=lambda req: (req.scheduled_for or req.created_at))
        return [_copy(req) for req in sorted_requests[:limit]]


@dataclass
class InMemoryExecutionTaskRepository(ExecutionTaskRepository):
    _tasks: dict[TaskId, ExecutionTask] = field(default_factory=dict)

    async def get(self, task_id: TaskId) -> ExecutionTask | None:
        return _copy(self._tasks.get(task_id))

    async def list_by_request(self, request_id: RequestId) -> Sequence[ExecutionTask]:
        return [_copy(task) for task in self._tasks.values() if task.request_id == request_id]

    async def add(self, task: ExecutionTask) -> None:
        self._tasks[task.id] = task

    async def update(self, task: ExecutionTask) -> None:
        if task.id not in self._tasks:
            msg = f"Task {task.id} not found"
            raise KeyError(msg)
        self._tasks[task.id] = task


@dataclass
class InMemoryEmailDigestRepository(EmailDigestRepository):
    _digests: dict[DigestId, EmailDigest] = field(default_factory=dict)

    async def get(self, digest_id: DigestId) -> EmailDigest | None:
        return _copy(self._digests.get(digest_id))

    async def add(self, digest: EmailDigest) -> None:
        self._digests[digest.id] = digest

    async def update(self, digest: EmailDigest) -> None:
        if digest.id not in self._digests:
            msg = f"Digest {digest.id} not found"
            raise KeyError(msg)
        self._digests[digest.id] = digest

    async def list_pending(self) -> Sequence[EmailDigest]:
        return [
            _copy(digest)
            for digest in self._digests.values()
            if digest.delivery_state
            in {digest.delivery_state.PENDING, digest.delivery_state.SENDING}
        ]


@dataclass
class InMemoryPositionSnapshotRepository(PositionSnapshotRepository):
    _snapshots: dict[PositionSnapshotId, PositionSnapshot] = field(default_factory=dict)

    async def get(self, snapshot_id: PositionSnapshotId) -> PositionSnapshot | None:
        return _copy(self._snapshots.get(snapshot_id))

    async def add(self, snapshot: PositionSnapshot) -> None:
        self._snapshots[snapshot.id] = snapshot

    async def list_recent(self, *, limit: int) -> Sequence[PositionSnapshot]:
        ordered = sorted(self._snapshots.values(), key=lambda snap: snap.captured_at, reverse=True)
        return [_copy(snapshot) for snapshot in ordered[:limit]]


@dataclass
class InMemoryPortfolioAccountRepository(PortfolioAccountRepository):
    _accounts: dict[tuple[StrategyId, ProviderId], PortfolioAccount] = field(default_factory=dict)

    async def get(
        self,
        strategy_id: StrategyId,
        provider_id: ProviderId,
    ) -> PortfolioAccount | None:
        return _copy(self._accounts.get((strategy_id, provider_id)))

    async def upsert(self, account: PortfolioAccount) -> None:
        key = (account.strategy_id, account.provider_id)
        self._accounts[key] = account

    async def list_for_strategy(self, strategy_id: StrategyId) -> Sequence[PortfolioAccount]:
        return [
            _copy(account)
            for (sid, _), account in self._accounts.items()
            if sid == strategy_id
        ]


@dataclass
class InMemoryPositionRepository(PositionRepository):
    _positions: dict[PositionId, Position] = field(default_factory=dict)

    async def get(self, position_id: PositionId) -> Position | None:
        return _copy(self._positions.get(position_id))

    async def add(self, position: Position) -> None:
        self._positions[position.id] = position

    async def update(self, position: Position) -> None:
        if position.id not in self._positions:
            msg = f"Position {position.id} not found"
            raise KeyError(msg)
        self._positions[position.id] = position

    async def list_open(
        self,
        strategy_id: StrategyId,
        provider_id: ProviderId | None = None,
    ) -> Sequence[Position]:
        results: list[Position] = []
        for position in self._positions.values():
            if position.strategy_id != strategy_id:
                continue
            if provider_id is not None and position.provider_id != provider_id:
                continue
            if position.closed_at is None:
                results.append(_copy(position))
        return results


@dataclass
class InMemoryOrderRepository(OrderRepository):
    _orders: dict[OrderId, Order] = field(default_factory=dict)

    async def get(self, order_id: OrderId) -> Order | None:
        return _copy(self._orders.get(order_id))

    async def add(self, order: Order) -> None:
        self._orders[order.id] = order

    async def update(self, order: Order) -> None:
        if order.id not in self._orders:
            msg = f"Order {order.id} not found"
            raise KeyError(msg)
        self._orders[order.id] = order

    async def list_recent(
        self,
        strategy_id: StrategyId,
        *,
        limit: int,
        provider_id: ProviderId | None = None,
    ) -> Sequence[Order]:
        filtered = [
            order
            for order in self._orders.values()
            if order.strategy_id == strategy_id
            and (provider_id is None or order.provider_id == provider_id)
        ]
        ordered = sorted(filtered, key=lambda order: order.placed_at, reverse=True)
        return [_copy(order) for order in ordered[:limit]]


@dataclass
class InMemoryRequestLogRepository(RequestLogRepository):
    _logs: dict[RequestId, list[Mapping[str, Any]]] = field(
        default_factory=lambda: defaultdict(list)
    )

    async def add(self, log_entry: Mapping[str, Any]) -> None:
        request_id = log_entry.get("request_id")
        if request_id is None:
            msg = "Log entry must include request_id"
            raise ValueError(msg)
        self._logs[request_id].append(dict(log_entry))

    async def list_for_request(self, request_id: RequestId) -> Sequence[Mapping[str, Any]]:
        return [dict(entry) for entry in self._logs.get(request_id, [])]


@dataclass
class InMemoryUnitOfWork(UnitOfWork):
    strategy_repository: InMemoryStrategyRepository = field(
        default_factory=InMemoryStrategyRepository
    )
    schedule_repository: InMemoryStrategyScheduleRepository = field(
        default_factory=InMemoryStrategyScheduleRepository
    )
    run_repository: InMemoryStrategyRunRepository = field(
        default_factory=InMemoryStrategyRunRepository
    )
    request_repository: InMemoryRequestRepository = field(
        default_factory=InMemoryRequestRepository
    )
    task_repository: InMemoryExecutionTaskRepository = field(
        default_factory=InMemoryExecutionTaskRepository
    )
    digest_repository: InMemoryEmailDigestRepository = field(
        default_factory=InMemoryEmailDigestRepository
    )
    portfolio_repository: InMemoryPortfolioAccountRepository = field(
        default_factory=InMemoryPortfolioAccountRepository
    )
    position_repository: InMemoryPositionRepository = field(
        default_factory=InMemoryPositionRepository
    )
    order_repository: InMemoryOrderRepository = field(
        default_factory=InMemoryOrderRepository
    )
    snapshot_repository: InMemoryPositionSnapshotRepository = field(
        default_factory=InMemoryPositionSnapshotRepository
    )
    log_repository: InMemoryRequestLogRepository = field(
        default_factory=InMemoryRequestLogRepository
    )
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def __aenter__(self) -> InMemoryUnitOfWork:
        await self._lock.acquire()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self._lock.release()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None
