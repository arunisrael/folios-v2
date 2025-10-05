"""Strategy domain models."""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import Annotated
from uuid import UUID

from pydantic import Field, field_validator

from .base import DomainModel
from .enums import ExecutionMode, ProviderId, StrategyRunStatus, StrategyStatus
from .types import IsoWeek, RunId, StrategyId


def utc_now() -> datetime:
    return datetime.now(UTC)


class RiskControls(DomainModel):
    """Risk management guardrails for a strategy."""

    max_position_size: Annotated[float, Field(ge=0.0, le=100.0)]
    max_exposure: Annotated[float, Field(ge=0.0, le=100.0)] = 95.0
    stop_loss: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    max_leverage: Annotated[float | None, Field(ge=0.0)] = None
    max_short_exposure: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    max_single_name_short: Annotated[float | None, Field(ge=0.0, le=100.0)] = None
    borrow_available: bool | None = None


class StrategyMetadata(DomainModel):
    """Descriptive metadata used in digests and research prompts."""

    description: str
    theme: str | None = None
    risk_level: str | None = None
    time_horizon: str | None = None
    key_metrics: tuple[str, ...] | None = None
    key_signals: tuple[str, ...] | None = None


class ProviderPreference(DomainModel):
    """Ordering of providers for a given strategy."""

    provider_id: ProviderId
    execution_modes: tuple[ExecutionMode, ...]
    rank: Annotated[int, Field(ge=1)] = 1

    @field_validator("execution_modes")
    @classmethod
    def ensure_modes(cls, value: tuple[ExecutionMode, ...]) -> tuple[ExecutionMode, ...]:
        if not value:
            msg = "At least one execution mode must be provided"
            raise ValueError(msg)
        return value


class Strategy(DomainModel):
    """Primary strategy definition stored in SQLite."""

    id: StrategyId
    name: Annotated[str, Field(min_length=1)]
    prompt: Annotated[str, Field(min_length=1)]
    tickers: tuple[str, ...]
    status: StrategyStatus = StrategyStatus.ACTIVE
    risk_controls: RiskControls | None = None
    metadata: StrategyMetadata | None = None
    preferred_providers: tuple[ProviderPreference, ...] = ()
    active_modes: tuple[ExecutionMode, ...] = (ExecutionMode.BATCH,)
    research_day: Annotated[int, Field(ge=1, le=5)] = 4  # default Thursday
    research_time_utc: time | None = None
    runtime_weight: Annotated[float, Field(gt=0.0)] = 1.0
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("tickers")
    @classmethod
    def normalize_tickers(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(ticker.strip().upper() for ticker in value if ticker.strip())
        return normalized

    @field_validator("active_modes")
    @classmethod
    def ensure_modes(cls, value: tuple[ExecutionMode, ...]) -> tuple[ExecutionMode, ...]:
        if not value:
            msg = "Strategies must declare at least one execution mode"
            raise ValueError(msg)
        return value


class StrategySchedule(DomainModel):
    """Weekly research assignment for a strategy."""

    strategy_id: StrategyId
    weekday: Annotated[int, Field(ge=1, le=5)]
    next_research_at: datetime | None = None
    last_research_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class StrategyRun(DomainModel):
    """Represents a single ISO-week run for a strategy."""

    id: RunId
    strategy_id: StrategyId
    week_of: datetime
    iso_week: IsoWeek
    status: StrategyRunStatus
    research_request_id: UUID | None = None
    execution_request_id: UUID | None = None
    monday_open_snapshot_id: UUID | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("iso_week")
    @classmethod
    def validate_iso_week(cls, value: IsoWeek) -> IsoWeek:
        year, week = value
        if not (1 <= week <= 53):
            msg = "ISO week must be between 1 and 53"
            raise ValueError(msg)
        if year < 2000:
            msg = "ISO week year must be >= 2000"
            raise ValueError(msg)
        return value

    @field_validator("week_of")
    @classmethod
    def normalize_week_of(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class StrategyRunNote(DomainModel):
    """Free-form note linked to a strategy run."""

    run_id: RunId
    message: str
    author: str
    created_at: datetime = Field(default_factory=utc_now)
