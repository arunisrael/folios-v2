"""Notification and snapshot domain models."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import Field, field_validator

from .base import DomainModel
from .enums import DeliveryState, DigestType
from .request import RequestPayloadRef
from .types import DigestId, IsoWeek, PositionSnapshotId, StrategyId


def utc_now() -> datetime:
    return datetime.now(UTC)


class PositionHolding(DomainModel):
    """Single position within a portfolio snapshot."""

    symbol: Annotated[str, Field(min_length=1)]
    quantity: Decimal
    average_cost: Decimal
    market_value: Decimal
    unrealized_gain: Decimal


class PositionSnapshot(DomainModel):
    """Immutable portfolio snapshot captured at a point in time."""

    id: PositionSnapshotId
    captured_at: datetime
    base_currency: str = "USD"
    holdings: tuple[PositionHolding, ...]
    total_equity: Decimal
    cash_balance: Decimal
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("captured_at", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class EmailDigest(DomainModel):
    """Sunday outlook or Friday recap email artifact."""

    id: DigestId
    digest_type: DigestType
    week_of: datetime
    iso_week: IsoWeek
    strategy_ids: tuple[StrategyId, ...]
    content_ref: RequestPayloadRef
    delivery_state: DeliveryState = DeliveryState.PENDING
    delivered_at: datetime | None = None
    failed_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @field_validator("week_of", "delivered_at", "failed_at", mode="before")
    @classmethod
    def ensure_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    @field_validator("strategy_ids")
    @classmethod
    def ensure_strategies(cls, value: tuple[StrategyId, ...]) -> tuple[StrategyId, ...]:
        if not value:
            msg = "Email digest must reference at least one strategy"
            raise ValueError(msg)
        return value
