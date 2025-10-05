"""Async SQLite unit of work implementation."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from types import TracebackType

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from folios_v2.persistence.interfaces import UnitOfWork

from .migrations import apply_migrations
from .repositories import (
    SQLiteEmailDigestRepository,
    SQLiteExecutionTaskRepository,
    SQLiteOrderRepository,
    SQLitePortfolioAccountRepository,
    SQLitePositionRepository,
    SQLitePositionSnapshotRepository,
    SQLiteRequestLogRepository,
    SQLiteRequestRepository,
    SQLiteStrategyRepository,
    SQLiteStrategyRunRepository,
    SQLiteStrategyScheduleRepository,
)

_migration_lock = asyncio.Lock()
_migrated_urls: set[str] = set()


async def _ensure_migrated(engine: AsyncEngine, database_url: str) -> None:
    async with _migration_lock:
        if database_url in _migrated_urls:
            return
        await apply_migrations(engine)
        _migrated_urls.add(database_url)


class SQLiteUnitOfWork(UnitOfWork):
    def __init__(
        self,
        engine: AsyncEngine,
        session_factory: async_sessionmaker[AsyncSession],
        database_url: str,
    ) -> None:
        self._engine = engine
        self._session_factory = session_factory
        self._database_url = database_url
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> SQLiteUnitOfWork:
        await _ensure_migrated(self._engine, self._database_url)
        self._session = self._session_factory()
        self.strategy_repository = SQLiteStrategyRepository(self._session)
        self.schedule_repository = SQLiteStrategyScheduleRepository(self._session)
        self.run_repository = SQLiteStrategyRunRepository(self._session)
        self.request_repository = SQLiteRequestRepository(self._session)
        self.task_repository = SQLiteExecutionTaskRepository(self._session)
        self.digest_repository = SQLiteEmailDigestRepository(self._session)
        self.portfolio_repository = SQLitePortfolioAccountRepository(self._session)
        self.position_repository = SQLitePositionRepository(self._session)
        self.order_repository = SQLiteOrderRepository(self._session)
        self.snapshot_repository = SQLitePositionSnapshotRepository(self._session)
        self.log_repository = SQLiteRequestLogRepository(self._session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None:
            await self._session.rollback()
        else:
            await self._session.commit()
        await self._session.close()
        self._session = None

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork session not started")
        await self._session.commit()

    async def rollback(self) -> None:
        if self._session is None:
            raise RuntimeError("UnitOfWork session not started")
        await self._session.rollback()


def create_sqlite_unit_of_work_factory(database_url: str) -> Callable[[], SQLiteUnitOfWork]:
    engine = create_async_engine(database_url, future=True)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    def factory() -> SQLiteUnitOfWork:
        return SQLiteUnitOfWork(engine, session_factory, database_url)

    return factory


__all__ = ["SQLiteUnitOfWork", "create_sqlite_unit_of_work_factory"]
