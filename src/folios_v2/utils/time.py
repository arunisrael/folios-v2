"""Time-related helpers."""

from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Normalize a datetime to UTC."""

    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
