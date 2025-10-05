from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from folios_v2.domain import ExecutionMode, Strategy, StrategyId, StrategyStatus


def test_strategy_ticker_normalization() -> None:
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="Momentum",
        prompt="Analyse.",
        tickers=(" aapl ", "msft"),
        status=StrategyStatus.ACTIVE,
    )
    assert strategy.tickers == ("AAPL", "MSFT")


def test_strategy_requires_execution_mode() -> None:
    with pytest.raises(ValidationError):
        Strategy(
            id=StrategyId(uuid4()),
            name="NoMode",
            prompt="Invalid",
            tickers=("AAPL",),
            status=StrategyStatus.ACTIVE,
            active_modes=(),
        )


def test_strategy_accepts_multiple_modes() -> None:
    strategy = Strategy(
        id=StrategyId(uuid4()),
        name="Dual",
        prompt="Run",
        tickers=("AAPL",),
        status=StrategyStatus.ACTIVE,
        active_modes=(ExecutionMode.BATCH, ExecutionMode.CLI),
    )
    assert ExecutionMode.CLI in strategy.active_modes
