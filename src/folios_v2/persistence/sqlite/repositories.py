"""SQLite repository implementations."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

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
)

from .models import (
    EmailDigestRecord,
    ExecutionTaskRecord,
    OrderRecord,
    PortfolioAccountRecord,
    PositionRecord,
    PositionSnapshotRecord,
    RequestLogRecord,
    RequestRecord,
    StrategyRecord,
    StrategyRunRecord,
    StrategyScheduleRecord,
)


def _now() -> datetime:
    return datetime.now(UTC)


class SQLiteStrategyRepository(StrategyRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, strategy_id: StrategyId) -> Strategy | None:
        record = await self._session.get(StrategyRecord, str(strategy_id))
        if record is None:
            return None
        return Strategy.model_validate(record.payload)

    async def list_active(self) -> Sequence[Strategy]:
        stmt: Select[tuple[StrategyRecord]] = select(StrategyRecord).where(
            StrategyRecord.status == "active"
        )
        result = await self._session.execute(stmt)
        return [Strategy.model_validate(r.payload) for r in result.scalars().all()]

    async def upsert(self, strategy: Strategy) -> None:
        record = await self._session.get(StrategyRecord, str(strategy.id))
        payload = strategy.model_dump(mode="json")
        if record is None:
            record = StrategyRecord(
                id=str(strategy.id),
                name=strategy.name,
                status=strategy.status.value,
                payload=payload,
            )
            self._session.add(record)
        else:
            record.name = strategy.name
            record.status = strategy.status.value
            record.payload = payload

    async def delete(self, strategy_id: StrategyId) -> None:
        record = await self._session.get(StrategyRecord, str(strategy_id))
        if record is not None:
            await self._session.delete(record)


class SQLiteStrategyScheduleRepository(StrategyScheduleRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, strategy_id: StrategyId) -> StrategySchedule | None:
        record = await self._session.get(StrategyScheduleRecord, str(strategy_id))
        if record is None:
            return None
        return StrategySchedule.model_validate(record.payload)

    async def upsert(self, schedule: StrategySchedule) -> None:
        record = await self._session.get(StrategyScheduleRecord, str(schedule.strategy_id))
        payload = schedule.model_dump(mode="json")
        if record is None:
            record = StrategyScheduleRecord(
                strategy_id=str(schedule.strategy_id),
                weekday=schedule.weekday,
                next_research_at=schedule.next_research_at,
                last_research_at=schedule.last_research_at,
                payload=payload,
            )
            self._session.add(record)
        else:
            record.weekday = schedule.weekday
            record.next_research_at = schedule.next_research_at
            record.last_research_at = schedule.last_research_at
            record.payload = payload

    async def list_all(self) -> Sequence[StrategySchedule]:
        result = await self._session.execute(select(StrategyScheduleRecord))
        return [StrategySchedule.model_validate(r.payload) for r in result.scalars().all()]


class SQLiteStrategyRunRepository(StrategyRunRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, run_id: RunId) -> StrategyRun | None:
        record = await self._session.get(StrategyRunRecord, str(run_id))
        if record is None:
            return None
        return StrategyRun.model_validate(record.payload)

    async def find_by_strategy_week(
        self,
        strategy_id: StrategyId,
        iso_week: tuple[int, int],
    ) -> StrategyRun | None:
        stmt = select(StrategyRunRecord).where(
            StrategyRunRecord.strategy_id == str(strategy_id),
            StrategyRunRecord.iso_year == iso_week[0],
            StrategyRunRecord.iso_week == iso_week[1],
        )
        result = await self._session.execute(stmt)
        record = result.scalars().first()
        return StrategyRun.model_validate(record.payload) if record else None

    async def add(self, run: StrategyRun) -> None:
        payload = run.model_dump(mode="json")
        record = StrategyRunRecord(
            id=str(run.id),
            strategy_id=str(run.strategy_id),
            iso_year=run.iso_week[0],
            iso_week=run.iso_week[1],
            status=run.status.value,
            payload=payload,
        )
        self._session.add(record)

    async def update(self, run: StrategyRun) -> None:
        record = await self._session.get(StrategyRunRecord, str(run.id))
        if record is None:
            raise KeyError(f"Strategy run {run.id} not found")
        record.iso_year = run.iso_week[0]
        record.iso_week = run.iso_week[1]
        record.status = run.status.value
        record.payload = run.model_dump(mode="json")


class SQLiteRequestRepository(RequestRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, request_id: RequestId) -> Request | None:
        record = await self._session.get(RequestRecord, str(request_id))
        if record is None:
            return None
        return Request.model_validate(record.payload)

    async def add(self, request: Request) -> None:
        payload = request.model_dump(mode="json")
        record = RequestRecord(
            id=str(request.id),
            strategy_id=str(request.strategy_id),
            provider_id=request.provider_id.value,
            mode=request.mode.value,
            request_type=request.request_type.value,
            priority=request.priority.value,
            lifecycle_state=request.lifecycle_state.value,
            scheduled_for=request.scheduled_for,
            started_at=request.started_at,
            completed_at=request.completed_at,
            created_at=request.created_at,
            updated_at=request.updated_at,
            payload=payload,
        )
        self._session.add(record)

    async def update(self, request: Request) -> None:
        record = await self._session.get(RequestRecord, str(request.id))
        if record is None:
            raise KeyError(f"Request {request.id} not found")
        record.provider_id = request.provider_id.value
        record.mode = request.mode.value
        record.request_type = request.request_type.value
        record.priority = request.priority.value
        record.lifecycle_state = request.lifecycle_state.value
        record.scheduled_for = request.scheduled_for
        record.started_at = request.started_at
        record.completed_at = request.completed_at
        record.updated_at = request.updated_at
        record.payload = request.model_dump(mode="json")

    async def list_pending(self, *, limit: int) -> Sequence[Request]:
        stmt = (
            select(RequestRecord)
            .where(RequestRecord.lifecycle_state.in_(
                ["pending", "scheduled"]
            ))
            .order_by(RequestRecord.scheduled_for.nulls_last(), RequestRecord.created_at)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [Request.model_validate(r.payload) for r in result.scalars().all()]


class SQLiteExecutionTaskRepository(ExecutionTaskRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: TaskId) -> ExecutionTask | None:
        record = await self._session.get(ExecutionTaskRecord, str(task_id))
        if record is None:
            return None
        return ExecutionTask.model_validate(record.payload)

    async def list_by_request(self, request_id: RequestId) -> Sequence[ExecutionTask]:
        stmt = select(ExecutionTaskRecord).where(
            ExecutionTaskRecord.request_id == str(request_id)
        )
        result = await self._session.execute(stmt)
        return [ExecutionTask.model_validate(r.payload) for r in result.scalars().all()]

    async def add(self, task: ExecutionTask) -> None:
        record = ExecutionTaskRecord(
            id=str(task.id),
            request_id=str(task.request_id),
            sequence=task.sequence,
            mode=task.mode.value,
            lifecycle_state=task.lifecycle_state.value,
            scheduled_for=task.scheduled_for,
            started_at=task.started_at,
            completed_at=task.completed_at,
            created_at=task.created_at,
            updated_at=task.updated_at,
            payload=task.model_dump(mode="json"),
        )
        self._session.add(record)

    async def update(self, task: ExecutionTask) -> None:
        record = await self._session.get(ExecutionTaskRecord, str(task.id))
        if record is None:
            raise KeyError(f"Task {task.id} not found")
        record.sequence = task.sequence
        record.mode = task.mode.value
        record.lifecycle_state = task.lifecycle_state.value
        record.scheduled_for = task.scheduled_for
        record.started_at = task.started_at
        record.completed_at = task.completed_at
        record.updated_at = task.updated_at
        record.payload = task.model_dump(mode="json")


class SQLiteEmailDigestRepository(EmailDigestRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, digest_id: DigestId) -> EmailDigest | None:
        record = await self._session.get(EmailDigestRecord, str(digest_id))
        if record is None:
            return None
        return EmailDigest.model_validate(record.payload)

    async def add(self, digest: EmailDigest) -> None:
        payload = digest.model_dump(mode="json")
        record = EmailDigestRecord(
            id=str(digest.id),
            digest_type=digest.digest_type.value,
            iso_year=digest.iso_week[0],
            iso_week=digest.iso_week[1],
            week_of=digest.week_of,
            delivery_state=digest.delivery_state.value,
            delivered_at=digest.delivered_at,
            failed_at=digest.failed_at,
            payload=payload,
        )
        self._session.add(record)

    async def update(self, digest: EmailDigest) -> None:
        record = await self._session.get(EmailDigestRecord, str(digest.id))
        if record is None:
            raise KeyError(f"Digest {digest.id} not found")
        record.digest_type = digest.digest_type.value
        record.iso_year = digest.iso_week[0]
        record.iso_week = digest.iso_week[1]
        record.week_of = digest.week_of
        record.delivery_state = digest.delivery_state.value
        record.delivered_at = digest.delivered_at
        record.failed_at = digest.failed_at
        record.payload = digest.model_dump(mode="json")

    async def list_pending(self) -> Sequence[EmailDigest]:
        stmt = select(EmailDigestRecord).where(
            EmailDigestRecord.delivery_state.in_(["pending", "sending"])
        )
        result = await self._session.execute(stmt)
        return [EmailDigest.model_validate(r.payload) for r in result.scalars().all()]


class SQLitePositionSnapshotRepository(PositionSnapshotRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, snapshot_id: PositionSnapshotId) -> PositionSnapshot | None:
        record = await self._session.get(PositionSnapshotRecord, str(snapshot_id))
        if record is None:
            return None
        return PositionSnapshot.model_validate(record.payload)

    async def add(self, snapshot: PositionSnapshot) -> None:
        payload = snapshot.model_dump(mode="json")
        record = PositionSnapshotRecord(
            id=str(snapshot.id),
            captured_at=snapshot.captured_at,
            payload=payload,
        )
        self._session.add(record)

    async def list_recent(self, *, limit: int) -> Sequence[PositionSnapshot]:
        stmt = (
            select(PositionSnapshotRecord)
            .order_by(PositionSnapshotRecord.captured_at.desc())
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [PositionSnapshot.model_validate(r.payload) for r in result.scalars().all()]


class SQLitePortfolioAccountRepository(PortfolioAccountRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(
        self,
        strategy_id: StrategyId,
        provider_id: ProviderId,
    ) -> PortfolioAccount | None:
        stmt = select(PortfolioAccountRecord).where(
            PortfolioAccountRecord.strategy_id == str(strategy_id),
            PortfolioAccountRecord.provider_id == provider_id.value,
        )
        result = await self._session.execute(stmt)
        record = result.scalars().first()
        return PortfolioAccount.model_validate(record.payload) if record else None

    async def upsert(self, account: PortfolioAccount) -> None:
        stmt = select(PortfolioAccountRecord).where(
            PortfolioAccountRecord.strategy_id == str(account.strategy_id),
            PortfolioAccountRecord.provider_id == account.provider_id.value,
        )
        result = await self._session.execute(stmt)
        record = result.scalars().first()
        payload = account.model_dump(mode="json")
        if record is None:
            record = PortfolioAccountRecord(
                strategy_id=str(account.strategy_id),
                provider_id=account.provider_id.value,
                payload=payload,
            )
            self._session.add(record)
        else:
            record.payload = payload

    async def list_for_strategy(self, strategy_id: StrategyId) -> Sequence[PortfolioAccount]:
        stmt = select(PortfolioAccountRecord).where(
            PortfolioAccountRecord.strategy_id == str(strategy_id)
        )
        result = await self._session.execute(stmt)
        return [PortfolioAccount.model_validate(r.payload) for r in result.scalars().all()]


class SQLitePositionRepository(PositionRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, position_id: PositionId) -> Position | None:
        record = await self._session.get(PositionRecord, str(position_id))
        if record is None:
            return None
        return Position.model_validate(record.payload)

    async def add(self, position: Position) -> None:
        record = PositionRecord(
            id=str(position.id),
            strategy_id=str(position.strategy_id),
            provider_id=position.provider_id.value if position.provider_id else None,
            symbol=position.symbol,
            status="open" if position.closed_at is None else "closed",
            opened_at=position.opened_at,
            closed_at=position.closed_at,
            payload=position.model_dump(mode="json"),
        )
        self._session.add(record)

    async def update(self, position: Position) -> None:
        record = await self._session.get(PositionRecord, str(position.id))
        if record is None:
            raise KeyError(f"Position {position.id} not found")
        record.provider_id = position.provider_id.value if position.provider_id else None
        record.symbol = position.symbol
        record.status = "open" if position.closed_at is None else "closed"
        record.opened_at = position.opened_at
        record.closed_at = position.closed_at
        record.payload = position.model_dump(mode="json")

    async def list_open(
        self,
        strategy_id: StrategyId,
        provider_id: ProviderId | None = None,
    ) -> Sequence[Position]:
        stmt = select(PositionRecord).where(
            PositionRecord.strategy_id == str(strategy_id),
            PositionRecord.status == "open",
        )
        if provider_id is not None:
            stmt = stmt.where(PositionRecord.provider_id == provider_id.value)
        result = await self._session.execute(stmt)
        return [Position.model_validate(r.payload) for r in result.scalars().all()]


class SQLiteOrderRepository(OrderRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, order_id: OrderId) -> Order | None:
        record = await self._session.get(OrderRecord, str(order_id))
        if record is None:
            return None
        return Order.model_validate(record.payload)

    async def add(self, order: Order) -> None:
        record = OrderRecord(
            id=str(order.id),
            strategy_id=str(order.strategy_id),
            provider_id=order.provider_id.value if order.provider_id else None,
            status=order.status,
            symbol=order.symbol,
            placed_at=order.placed_at,
            payload=order.model_dump(mode="json"),
        )
        self._session.add(record)

    async def update(self, order: Order) -> None:
        record = await self._session.get(OrderRecord, str(order.id))
        if record is None:
            raise KeyError(f"Order {order.id} not found")
        record.provider_id = order.provider_id.value if order.provider_id else None
        record.status = order.status
        record.symbol = order.symbol
        record.placed_at = order.placed_at
        record.payload = order.model_dump(mode="json")

    async def list_recent(
        self,
        strategy_id: StrategyId,
        *,
        limit: int,
        provider_id: ProviderId | None = None,
    ) -> Sequence[Order]:
        stmt = select(OrderRecord).where(OrderRecord.strategy_id == str(strategy_id))
        if provider_id is not None:
            stmt = stmt.where(OrderRecord.provider_id == provider_id.value)
        stmt = stmt.order_by(OrderRecord.placed_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [Order.model_validate(r.payload) for r in result.scalars().all()]


class SQLiteRequestLogRepository(RequestLogRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, log_entry: Mapping[str, object]) -> None:
        attributes_value = log_entry.get("attributes")
        if isinstance(attributes_value, Mapping):
            attributes_dict = dict(attributes_value)
        else:
            attributes_dict = {}
        created_at = log_entry.get("created_at")
        created_ts = created_at if isinstance(created_at, datetime) else _now()
        record = RequestLogRecord(
            request_id=str(log_entry.get("request_id")),
            task_id=log_entry.get("task_id"),
            previous_state=log_entry.get("previous_state"),
            next_state=str(log_entry.get("next_state")),
            message=log_entry.get("message"),
            created_at=created_ts,
            attributes=attributes_dict,
        )
        self._session.add(record)

    async def list_for_request(self, request_id: RequestId) -> Sequence[Mapping[str, object]]:
        stmt = select(RequestLogRecord).where(RequestLogRecord.request_id == str(request_id))
        result = await self._session.execute(stmt)
        return [
            {
                "request_id": record.request_id,
                "task_id": record.task_id,
                "previous_state": record.previous_state,
                "next_state": record.next_state,
                "message": record.message,
                "created_at": record.created_at,
                "attributes": record.attributes,
            }
            for record in result.scalars().all()
        ]


__all__ = [
    "SQLiteEmailDigestRepository",
    "SQLiteExecutionTaskRepository",
    "SQLiteOrderRepository",
    "SQLitePortfolioAccountRepository",
    "SQLitePositionRepository",
    "SQLitePositionSnapshotRepository",
    "SQLiteRequestLogRepository",
    "SQLiteRequestRepository",
    "SQLiteStrategyRepository",
    "SQLiteStrategyRunRepository",
    "SQLiteStrategyScheduleRepository",
]
