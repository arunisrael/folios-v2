from __future__ import annotations

from uuid import uuid4

from folios_v2.domain import StrategyId, StrategySchedule
from folios_v2.scheduling import WeekdayLoadBalancer


def test_load_balancer_assigns_lightest_day() -> None:
    load_balancer = WeekdayLoadBalancer()
    strategy_a = StrategySchedule(strategy_id=StrategyId(uuid4()), weekday=2)
    strategy_b = StrategySchedule(strategy_id=StrategyId(uuid4()), weekday=4)
    schedules = (strategy_a, strategy_b)
    weights = {
        strategy_a.strategy_id: 2.0,
        strategy_b.strategy_id: 1.0,
    }

    chosen_day = load_balancer.choose_day(schedules, weights, new_strategy_weight=1.0)
    assert chosen_day in {1, 3, 5}


def test_load_balancer_respects_existing_load() -> None:
    load_balancer = WeekdayLoadBalancer()
    strat_ids = [StrategyId(uuid4()) for _ in range(3)]
    schedules = (
        StrategySchedule(strategy_id=strat_ids[0], weekday=1),
        StrategySchedule(strategy_id=strat_ids[1], weekday=1),
        StrategySchedule(strategy_id=strat_ids[2], weekday=3),
    )
    weights = {strat_ids[0]: 1.0, strat_ids[1]: 1.0, strat_ids[2]: 1.0}

    chosen_day = load_balancer.choose_day(schedules, weights, new_strategy_weight=1.0)
    assert chosen_day in {2, 4, 5}
