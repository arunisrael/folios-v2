from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

from folios_v2.domain import (
    ExecutionMode,
    ProviderId,
    RequestPriority,
    RequestType,
    ScreenerProviderId,
    Strategy,
    StrategyId,
    StrategyScreener,
    StrategyStatus,
)
from folios_v2.orchestration.prompt_builder import build_research_prompt
from folios_v2.orchestration.portfolio_snapshot import PortfolioSnapshot, PositionSummary
from folios_v2.orchestration import RequestOrchestrator, StrategyCoordinator
from folios_v2.persistence import InMemoryUnitOfWork, UnitOfWork
from folios_v2.providers import ProviderPlugin, ProviderRegistry, ProviderThrottle, ResultParser
from folios_v2.scheduling import HolidayCalendar, WeekdayLoadBalancer
from folios_v2.screeners import ScreenerResult, ScreenerService


class DummyParser(ResultParser):
    async def parse(self, ctx: object) -> dict[str, str]:  # type: ignore[override]
        return {"status": "ok"}


async def _store_strategy(uow: InMemoryUnitOfWork, strategy: Strategy) -> None:
    async with uow as session:
        await session.strategy_repository.upsert(strategy)
        await session.commit()


def _factory(uow: InMemoryUnitOfWork) -> UnitOfWork:
    return uow


class StubScreenerProvider:
    provider_id = ScreenerProviderId.FINNHUB

    async def screen(
        self,
        *,
        filters: Mapping[str, object],
        limit: int,
        universe_cap: int | None = None,
    ) -> ScreenerResult:
        return ScreenerResult(
            provider=self.provider_id,
            symbols=("AAPL", "MSFT"),
            filters=dict(filters),
            metadata={"limit": limit, "universe_cap": universe_cap},
        )


def test_build_research_prompt_includes_snapshot_section() -> None:
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="SnapshotTest",
        prompt="Base strategy prompt.",
        tickers=(),
        status=StrategyStatus.ACTIVE,
    )
    snapshot = PortfolioSnapshot(
        strategy_id=strategy.id,
        provider_id=ProviderId.OPENAI,
        cash=Decimal("20000"),
        positions_value=Decimal("80000"),
        total_value=Decimal("100000"),
        gross_exposure_pct=Decimal("80"),
        net_exposure_pct=Decimal("60"),
        leverage=Decimal("0.80"),
        updated_at=datetime(2025, 10, 18, 5, 3, tzinfo=UTC),
        positions=[
            PositionSummary(
                symbol="AAPL",
                side="long",
                quantity=Decimal("10"),
                average_price=Decimal("150"),
                market_price=Decimal("170"),
                market_value=Decimal("1700"),
                unrealized_pl=Decimal("200"),
                unrealized_pl_pct=Decimal("0.1333"),
                weight_pct=Decimal("1.7"),
            )
        ],
    )

    prompt = build_research_prompt(
        strategy,
        mode=ExecutionMode.BATCH,
        portfolio_snapshot=snapshot,
    )

    assert "Current Portfolio Snapshot — OPENAI" in prompt
    assert "Cash: $20,000.00" in prompt
    assert "Gross exposure: 80.0%" in prompt
    assert "AAPL | long" in prompt
    assert prompt.count("Base strategy prompt.") == 1


def test_ensure_schedule_uses_research_day() -> None:
    uow = InMemoryUnitOfWork()
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="ScheduleTest",
        prompt="prompt",
        tickers=("AAPL",),
        status=StrategyStatus.ACTIVE,
        research_day=2,
    )
    asyncio.run(_store_strategy(uow, strategy))

    coordinator = StrategyCoordinator(
        lambda: _factory(uow),
        WeekdayLoadBalancer(),
        HolidayCalendar(),
    )
    schedule = asyncio.run(coordinator.ensure_schedule(strategy))
    assert schedule.weekday == 2


def test_ensure_weekly_runs_creates_entries() -> None:
    uow = InMemoryUnitOfWork()
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="WeekRun",
        prompt="prompt",
        tickers=("AAPL",),
        status=StrategyStatus.ACTIVE,
        research_day=2,
    )
    asyncio.run(_store_strategy(uow, strategy))

    coordinator = StrategyCoordinator(
        lambda: _factory(uow),
        WeekdayLoadBalancer(),
        HolidayCalendar(),
    )
    created = asyncio.run(coordinator.ensure_weekly_runs((2025, 10)))
    assert len(created) == 1
    assert created[0].iso_week == (2025, 10)


def test_request_orchestrator_creates_request_and_task(tmp_path: Path) -> None:
    uow = InMemoryUnitOfWork()
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="Requester",
        prompt="prompt",
        tickers=("AAPL",),
        status=StrategyStatus.ACTIVE,
        research_day=2,
    )
    asyncio.run(_store_strategy(uow, strategy))

    plugin = ProviderPlugin(
        provider_id=ProviderId.OPENAI,
        display_name="Mock",
        supports_batch=True,
        supports_cli=False,
        default_mode=ExecutionMode.BATCH,
        throttle=ProviderThrottle(max_concurrent=1),
        parser=DummyParser(),
        batch_executor=None,
    )
    registry = ProviderRegistry()
    registry.register(plugin)

    orchestrator = RequestOrchestrator(
        lambda: _factory(uow),
        registry,
        tmp_path,
    )
    request, task = asyncio.run(
        orchestrator.enqueue_request(
            strategy,
            provider_id=ProviderId.OPENAI,
            request_type=RequestType.RESEARCH,
            mode=ExecutionMode.BATCH,
            priority=RequestPriority.HIGH,
            scheduled_for=datetime(2025, 3, 17, 12, tzinfo=UTC),
        )
    )

    assert request.provider_id == ProviderId.OPENAI
    assert task.request_id == request.id
    enriched_prompt = request.metadata["strategy_prompt"]
    assert enriched_prompt.startswith("prompt")
    assert "Recency requirements" in enriched_prompt
    assert request.metadata["output_schema"] == "investment_analysis_v1"

    async def _lookup() -> None:
        async with uow as session:
            stored = await session.request_repository.get(request.id)
            assert stored is not None

    asyncio.run(_lookup())


def test_request_orchestrator_refreshes_screener(tmp_path: Path) -> None:
    uow = InMemoryUnitOfWork()
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="Screener",
        prompt="prompt",
        tickers=("OLD",),
        status=StrategyStatus.ACTIVE,
        research_day=2,
        screener=StrategyScreener(
            provider=ScreenerProviderId.FINNHUB,
            filters={"market_cap_min": 1_000_000_000},
            limit=5,
        ),
    )
    asyncio.run(_store_strategy(uow, strategy))

    plugin = ProviderPlugin(
        provider_id=ProviderId.OPENAI,
        display_name="Mock",
        supports_batch=True,
        supports_cli=False,
        default_mode=ExecutionMode.BATCH,
        throttle=ProviderThrottle(max_concurrent=1),
        parser=DummyParser(),
        batch_executor=None,
    )
    registry = ProviderRegistry()
    registry.register(plugin)

    service = ScreenerService()
    service.register(StubScreenerProvider())

    orchestrator = RequestOrchestrator(
        lambda: _factory(uow),
        registry,
        tmp_path,
        screener_service=service,
    )

    request, _ = asyncio.run(
        orchestrator.enqueue_request(
            strategy,
            provider_id=ProviderId.OPENAI,
            request_type=RequestType.RESEARCH,
            mode=ExecutionMode.BATCH,
            priority=RequestPriority.NORMAL,
        )
    )

    assert request.metadata["screener_candidates"] == "AAPL,MSFT"
    assert request.metadata["screener_provider"] == ScreenerProviderId.FINNHUB.value
    prompt = request.metadata["strategy_prompt"]
    assert "Screened ticker candidates" in prompt
    assert "AAPL" in prompt

    async def _check_strategy() -> None:
        async with uow as session:
            updated = await session.strategy_repository.get(strategy.id)
            assert updated is not None
            assert updated.tickers == ("AAPL", "MSFT")

    asyncio.run(_check_strategy())
