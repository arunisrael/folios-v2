"""Strategy coordination and scheduling services."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from folios_v2.domain import Strategy, StrategyId, StrategyRun, StrategyRunStatus, StrategySchedule
from folios_v2.domain.types import IsoWeek, RunId
from folios_v2.persistence import UnitOfWork
from folios_v2.scheduling import HolidayCalendar, WeekdayLoadBalancer
from folios_v2.utils import ensure_utc

UnitOfWorkFactory = Callable[[], UnitOfWork]


class StrategyCoordinator:
    """Ensures strategies are scheduled and weekly runs are maintained."""

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        load_balancer: WeekdayLoadBalancer,
        calendar: HolidayCalendar,
    ) -> None:
        self._uow_factory = uow_factory
        self._load_balancer = load_balancer
        self._calendar = calendar

    async def ensure_schedule(self, strategy: Strategy) -> StrategySchedule:
        async with self._uow_factory() as uow:
            existing = await uow.schedule_repository.get(strategy.id)
            if existing is not None:
                return existing

            schedules = await uow.schedule_repository.list_all()
            weights = await self._collect_runtime_weights(uow)
            if strategy.research_day:
                weekday = strategy.research_day
            else:
                weekday = self._load_balancer.choose_day(
                    schedules,
                    weights,
                    new_strategy_weight=strategy.runtime_weight,
                )

            schedule = StrategySchedule(
                strategy_id=strategy.id,
                weekday=weekday,
            )
            await uow.schedule_repository.upsert(schedule)
            await uow.commit()
            return schedule

    async def _collect_runtime_weights(self, uow: UnitOfWork) -> dict[StrategyId, float]:
        active_strategies = await uow.strategy_repository.list_active()
        return {strategy.id: strategy.runtime_weight for strategy in active_strategies}

    async def ensure_weekly_runs(self, iso_week: IsoWeek) -> Sequence[StrategyRun]:
        """Ensure each active strategy has a run row for the requested ISO week."""

        created: list[StrategyRun] = []
        async with self._uow_factory() as uow:
            strategies = await uow.strategy_repository.list_active()
            week_of = datetime.fromisocalendar(iso_week[0], iso_week[1], 1).replace(tzinfo=UTC)
            for strategy in strategies:
                existing = await uow.run_repository.find_by_strategy_week(strategy.id, iso_week)
                if existing is not None:
                    continue
                run = StrategyRun(
                    id=RunId(uuid4()),
                    strategy_id=strategy.id,
                    week_of=week_of,
                    iso_week=iso_week,
                    status=StrategyRunStatus.PLANNED,
                )
                await uow.run_repository.add(run)
                created.append(run)
            if created:
                await uow.commit()
        return tuple(created)

    async def monday_execution_window(self, reference: datetime) -> datetime:
        """Return the next valid Monday open respecting the holiday calendar."""

        current = ensure_utc(reference)
        candidate_date = current.date()
        if current.weekday() != 0:
            days_until = (7 - current.weekday()) % 7
            if days_until == 0:
                days_until = 7
            candidate_date = candidate_date + timedelta(days=days_until)
        else:
            open_dt = datetime.combine(
                candidate_date,
                self._calendar.open_time,
                tzinfo=UTC,
            )
            if open_dt <= current:
                candidate_date = candidate_date + timedelta(days=7)

        while not self._calendar.is_open_day(candidate_date):
            candidate_date = candidate_date + timedelta(days=7)

        return datetime.combine(
            candidate_date,
            self._calendar.open_time,
            tzinfo=UTC,
        )


__all__ = ["StrategyCoordinator"]
