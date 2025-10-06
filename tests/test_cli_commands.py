from __future__ import annotations

import asyncio
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from importlib import import_module

app_module = import_module("folios_v2.cli.app")
from folios_v2.cli.app import app
from folios_v2.cli.deps import reset_container
from folios_v2.domain import (
    ScreenerProviderId,
    Strategy,
    StrategyId,
    StrategyScreener,
    StrategyStatus,
)
from folios_v2.persistence import InMemoryUnitOfWork
from folios_v2.screeners import ScreenerResult, ScreenerService


def _env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    db_url = f"sqlite+aiosqlite:///{tmp_path/'cli.db'}"
    monkeypatch.setenv("FOLIOS_DATABASE_URL", db_url)
    monkeypatch.setenv("FOLIOS_ARTIFACTS_ROOT", str(tmp_path / "artifacts"))
    monkeypatch.setenv("FOLIOS_ENV", "test")
    reset_container()


class CliStubProvider:
    provider_id = ScreenerProviderId.FINNHUB

    async def screen(
        self,
        *,
        filters: Mapping[str, Any],
        limit: int,
        universe_cap: int | None = None,
    ) -> ScreenerResult:
        return ScreenerResult(
            provider=self.provider_id,
            symbols=("AAPL", "MSFT"),
            filters=dict(filters),
            metadata={"limit": limit, "universe_cap": universe_cap},
        )


class StubContainer:
    def __init__(self, uow: InMemoryUnitOfWork, service: ScreenerService) -> None:
        self.unit_of_work_factory = lambda: uow
        self.screener_service = service


async def _store_strategy(uow: InMemoryUnitOfWork, strategy: Strategy) -> None:
    async with uow as session:
        await session.strategy_repository.upsert(strategy)
        await session.commit()

def test_cli_seed_and_list(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "seed-strategy",
            "Momentum",
            "Study",
            "--tickers",
            "AAPL,MSFT",
        ],
    )
    assert result.exit_code == 0
    created_id = result.stdout.strip().split()[-1]

    list_result = runner.invoke(app, ["list-strategies"])
    assert list_result.exit_code == 0
    assert "Momentum" in list_result.stdout

    ensure_result = runner.invoke(app, ["ensure-schedule", created_id])
    assert ensure_result.exit_code == 0
    assert "weekday" in ensure_result.stdout

    plan_result = runner.invoke(app, ["plan-week", "2025", "10"])
    assert plan_result.exit_code == 0


def test_cli_show_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _env(monkeypatch, tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["show-settings"])
    assert result.exit_code == 0
    assert "Environment:\t" in result.stdout


def test_cli_screener_run(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ScreenerService()
    service.register(CliStubProvider())
    uow = InMemoryUnitOfWork()

    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="CLI",
        prompt="prompt",
        tickers=("OLD",),
        status=StrategyStatus.ACTIVE,
        screener=StrategyScreener(
            provider=ScreenerProviderId.FINNHUB,
            filters={"market_cap_min": 1_000_000_000},
            limit=5,
        ),
    )
    asyncio.run(_store_strategy(uow, strategy))

    container = StubContainer(uow, service)
    monkeypatch.setattr(app_module, "get_container", lambda: container)

    runner = CliRunner()
    result = runner.invoke(app, ["screener", "run", str(strategy.id)])

    assert result.exit_code == 0
    assert "Candidates (2): AAPL, MSFT" in result.stdout

    async def _fetch() -> Strategy | None:
        async with uow as session:
            stored = await session.strategy_repository.get(strategy.id)
            await session.commit()
        return stored

    stored_strategy = asyncio.run(_fetch())
    assert stored_strategy is not None
    assert stored_strategy.tickers == ("AAPL", "MSFT")


def test_cli_screener_inspect(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ScreenerService()
    service.register(CliStubProvider())
    uow = InMemoryUnitOfWork()

    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="Inspect",
        prompt="prompt",
        tickers=("AAPL", "MSFT"),
        status=StrategyStatus.ACTIVE,
        screener=StrategyScreener(
            provider=ScreenerProviderId.FINNHUB,
            filters={"market_cap_min": 1_000_000_000},
            limit=5,
            universe_cap=500,
        ),
    )
    asyncio.run(_store_strategy(uow, strategy))

    container = StubContainer(uow, service)
    monkeypatch.setattr(app_module, "get_container", lambda: container)

    runner = CliRunner()
    result = runner.invoke(app, ["screener", "inspect", str(strategy.id)])

    assert result.exit_code == 0
    assert "Screener provider: finnhub" in result.stdout
    assert "Universe cap: 500" in result.stdout
