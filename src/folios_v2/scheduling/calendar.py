"""Holiday-aware scheduling utilities."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta

from folios_v2.utils import ensure_utc


class HolidayCalendar:
    """Minimal holiday calendar aware of market open windows."""

    def __init__(
        self,
        *,
        holidays: Iterable[date] | None = None,
        open_weekdays: set[int] | None = None,
        open_time: time = time(9, 30),
    ) -> None:
        self._holidays = {holiday for holiday in (holidays or [])}
        self._open_weekdays = open_weekdays or {0, 1, 2, 3, 4}
        self._open_time = open_time

    def add_holiday(self, holiday: date) -> None:
        self._holidays.add(holiday)

    def is_holiday(self, target: date) -> bool:
        return target in self._holidays

    def is_open_day(self, target: date) -> bool:
        return target.weekday() in self._open_weekdays and target not in self._holidays

    @property
    def open_time(self) -> time:
        return self._open_time

    def next_open(self, after: datetime) -> datetime:
        current = ensure_utc(after)
        search_date = current.date()
        while True:
            if self.is_open_day(search_date):
                candidate = datetime.combine(search_date, self._open_time, tzinfo=UTC)
                if candidate >= current:
                    return candidate
            search_date += timedelta(days=1)


__all__ = ["HolidayCalendar"]
