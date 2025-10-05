from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from folios_v2.domain import (
    ExecutionMode,
    LifecycleState,
    Order,
    OrderAction,
    PortfolioAccount,
    Position,
    PositionSide,
    Request,
    RequestPriority,
    RequestType,
    Strategy,
    StrategyId,
    StrategyStatus,
)
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.types import OrderId, PositionId, RequestId
from folios_v2.persistence.sqlite import create_sqlite_unit_of_work_factory


def _db_url(tmp_path: Path) -> str:
    db_file = tmp_path / "folios.db"
    return f"sqlite+aiosqlite:///{db_file}"


def test_sqlite_strategy_round_trip(tmp_path: Path) -> None:
    factory = create_sqlite_unit_of_work_factory(_db_url(tmp_path))
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="Growth",
        prompt="Do research",
        tickers=("AAPL", "MSFT"),
        status=StrategyStatus.ACTIVE,
    )

    async def _store() -> None:
        async with factory() as uow:
            await uow.strategy_repository.upsert(strategy)
            await uow.commit()

    asyncio.run(_store())

    async def _load() -> Strategy | None:
        async with factory() as uow:
            return await uow.strategy_repository.get(strategy.id)

    loaded = asyncio.run(_load())
    assert loaded is not None
    assert loaded.model_dump() == strategy.model_dump()


def test_sqlite_portfolio_position_order(tmp_path: Path) -> None:
    factory = create_sqlite_unit_of_work_factory(_db_url(tmp_path))
    strategy_id = StrategyId(uuid4())
    provider = ProviderId.OPENAI

    strategy = Strategy(
        id=strategy_id,
        name="Value",
        prompt="Analyze",
        tickers=("GOOG",),
        status=StrategyStatus.ACTIVE,
    )

    account = PortfolioAccount(
        strategy_id=strategy_id,
        provider_id=provider,
        cash_balance=Decimal("100000"),
        equity_value=Decimal("0"),
    )

    position = Position(
        id=PositionId(uuid4()),
        strategy_id=strategy_id,
        provider_id=provider,
        symbol="GOOG",
        side=PositionSide.LONG,
        quantity=Decimal("10"),
        average_price=Decimal("120.50"),
    )

    order = Order(
        id=OrderId(uuid4()),
        strategy_id=strategy_id,
        provider_id=provider,
        symbol="GOOG",
        action=OrderAction.BUY,
        quantity=Decimal("10"),
        limit_price=Decimal("120.50"),
    )

    async def _store() -> None:
        async with factory() as uow:
            await uow.strategy_repository.upsert(strategy)
            await uow.portfolio_repository.upsert(account)
            await uow.position_repository.add(position)
            await uow.order_repository.add(order)
            await uow.commit()

    asyncio.run(_store())

    async def _load() -> tuple[list[PortfolioAccount], list[Position], list[Order]]:
        async with factory() as uow:
            accounts = await uow.portfolio_repository.list_for_strategy(strategy_id)
            positions = await uow.position_repository.list_open(strategy_id, provider)
            orders = await uow.order_repository.list_recent(
                strategy_id,
                limit=10,
                provider_id=provider,
            )
            return list(accounts), list(positions), list(orders)

    accounts, positions, orders = asyncio.run(_load())
    assert accounts and accounts[0].cash_balance == Decimal("100000")
    assert positions and positions[0].symbol == "GOOG"
    assert orders and orders[0].symbol == "GOOG"


def test_sqlite_requests_and_tasks(tmp_path: Path) -> None:
    factory = create_sqlite_unit_of_work_factory(_db_url(tmp_path))
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="Momentum",
        prompt="study",
        tickers=("TSLA",),
        status=StrategyStatus.ACTIVE,
    )
    request = Request(
        id=RequestId(uuid4()),
        strategy_id=strategy.id,
        provider_id=ProviderId.OPENAI,
        mode=ExecutionMode.CLI,
        request_type=RequestType.RESEARCH,
        priority=RequestPriority.HIGH,
        lifecycle_state=LifecycleState.SCHEDULED,
        scheduled_for=datetime.now(UTC),
        metadata={"k": "v"},
    )

    async def _store() -> None:
        async with factory() as uow:
            await uow.strategy_repository.upsert(strategy)
            await uow.request_repository.add(request)
            await uow.commit()

    asyncio.run(_store())

    async def _load() -> Request | None:
        async with factory() as uow:
            pending = await uow.request_repository.list_pending(limit=5)
            return pending[0] if pending else None

    loaded = asyncio.run(_load())
    assert loaded is not None
    assert loaded.metadata["k"] == "v"
