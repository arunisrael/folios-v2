"""Persistence layer abstractions for repositories and unit of work."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from types import TracebackType
from typing import Protocol

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


class StrategyRepository(Protocol):
    """CRUD operations for strategies."""

    async def get(self, strategy_id: StrategyId) -> Strategy | None: ...

    async def list_active(self) -> Sequence[Strategy]: ...

    async def upsert(self, strategy: Strategy) -> None: ...

    async def delete(self, strategy_id: StrategyId) -> None: ...


class StrategyScheduleRepository(Protocol):
    """Read/write access to strategy scheduling assignments."""

    async def get(self, strategy_id: StrategyId) -> StrategySchedule | None: ...

    async def upsert(self, schedule: StrategySchedule) -> None: ...

    async def list_all(self) -> Sequence[StrategySchedule]: ...


class StrategyRunRepository(Protocol):
    """Weekly strategy run tracking."""

    async def get(self, run_id: RunId) -> StrategyRun | None: ...

    async def find_by_strategy_week(
        self,
        strategy_id: StrategyId,
        iso_week: tuple[int, int],
    ) -> StrategyRun | None: ...

    async def add(self, run: StrategyRun) -> None: ...

    async def update(self, run: StrategyRun) -> None: ...


class RequestRepository(Protocol):
    """Lifecycle management for requests."""

    async def get(self, request_id: RequestId) -> Request | None: ...

    async def add(self, request: Request) -> None: ...

    async def update(self, request: Request) -> None: ...

    async def list_pending(self, *, limit: int) -> Sequence[Request]: ...


class ExecutionTaskRepository(Protocol):
    """Storage for execution tasks belonging to requests."""

    async def get(self, task_id: TaskId) -> ExecutionTask | None: ...

    async def list_by_request(self, request_id: RequestId) -> Sequence[ExecutionTask]: ...

    async def add(self, task: ExecutionTask) -> None: ...

    async def update(self, task: ExecutionTask) -> None: ...


class EmailDigestRepository(Protocol):
    """Persistence for generated email digests."""

    async def get(self, digest_id: DigestId) -> EmailDigest | None: ...

    async def add(self, digest: EmailDigest) -> None: ...

    async def update(self, digest: EmailDigest) -> None: ...

    async def list_pending(self) -> Sequence[EmailDigest]: ...


class PositionSnapshotRepository(Protocol):
    """Persistence for captured portfolio snapshots."""

    async def get(self, snapshot_id: PositionSnapshotId) -> PositionSnapshot | None: ...

    async def add(self, snapshot: PositionSnapshot) -> None: ...

    async def list_recent(self, *, limit: int) -> Sequence[PositionSnapshot]: ...


class PortfolioAccountRepository(Protocol):
    """Persistence for strategy/provider portfolio accounts."""

    async def get(
        self,
        strategy_id: StrategyId,
        provider_id: ProviderId,
    ) -> PortfolioAccount | None: ...

    async def upsert(self, account: PortfolioAccount) -> None: ...

    async def list_for_strategy(self, strategy_id: StrategyId) -> Sequence[PortfolioAccount]: ...


class PositionRepository(Protocol):
    """Storage for trading positions."""

    async def get(self, position_id: PositionId) -> Position | None: ...

    async def add(self, position: Position) -> None: ...

    async def update(self, position: Position) -> None: ...

    async def list_open(
        self,
        strategy_id: StrategyId,
        provider_id: ProviderId | None = None,
    ) -> Sequence[Position]: ...


class OrderRepository(Protocol):
    """Persistence for orders."""

    async def get(self, order_id: OrderId) -> Order | None: ...

    async def add(self, order: Order) -> None: ...

    async def update(self, order: Order) -> None: ...

    async def list_recent(
        self,
        strategy_id: StrategyId,
        *,
        limit: int,
        provider_id: ProviderId | None = None,
    ) -> Sequence[Order]: ...


class RequestLogRepository(Protocol):
    """Storage for request/task lifecycle log entries."""

    async def add(self, log_entry: Mapping[str, object]) -> None: ...

    async def list_for_request(self, request_id: RequestId) -> Sequence[Mapping[str, object]]: ...


class UnitOfWork(Protocol):
    """Transactional boundary for repository operations."""

    strategy_repository: StrategyRepository
    schedule_repository: StrategyScheduleRepository
    run_repository: StrategyRunRepository
    request_repository: RequestRepository
    task_repository: ExecutionTaskRepository
    digest_repository: EmailDigestRepository
    portfolio_repository: PortfolioAccountRepository
    position_repository: PositionRepository
    order_repository: OrderRepository
    snapshot_repository: PositionSnapshotRepository
    log_repository: RequestLogRepository

    async def __aenter__(self) -> UnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...
