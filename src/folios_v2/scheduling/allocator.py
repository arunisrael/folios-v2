"""Strategy weekday allocation utilities."""

from __future__ import annotations

import heapq
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from folios_v2.domain import StrategyId, StrategySchedule

from .exceptions import SchedulingError


@dataclass(slots=True)
class WeekdayLoadBalancer:
    """Assigns strategies to weekdays while balancing cumulative runtime weights."""

    weekdays: tuple[int, ...] = (1, 2, 3, 4, 5)
    default_weight: float = 1.0
    tolerance: float = 0.0

    def choose_day(
        self,
        schedules: Sequence[StrategySchedule],
        weights: Mapping[StrategyId, float],
        *,
        new_strategy_weight: float,
    ) -> int:
        if new_strategy_weight <= 0:
            msg = "Strategy weight must be positive"
            raise SchedulingError(msg)

        heap: list[tuple[float, int]] = []
        for weekday in self.weekdays:
            total_weight = self._total_weight_for_day(schedules, weights, weekday)
            heapq.heappush(heap, (total_weight, weekday))

        load, weekday = heapq.heappop(heap)
        # Optional tolerance: if spread is too uneven, this signals need to rebalance externally.
        if heap:
            min_load = load
            max_load = max(weight for weight, _ in heap)
            if self.tolerance > 0 and (max_load - min_load) > self.tolerance:
                # In future phases we can trigger a rebalance; for now just proceed.
                pass
        return weekday

    def _total_weight_for_day(
        self,
        schedules: Sequence[StrategySchedule],
        weights: Mapping[StrategyId, float],
        weekday: int,
    ) -> float:
        total = 0.0
        for schedule in schedules:
            if schedule.weekday != weekday:
                continue
            total += weights.get(schedule.strategy_id, self.default_weight)
        return total


__all__ = ["WeekdayLoadBalancer"]
