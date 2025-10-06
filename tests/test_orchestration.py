from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
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
