"""Trading domain models for portfolios, positions, and orders."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import Field, field_validator

from .base import DomainModel
from .enums import ProviderId
from .types import OrderId, PositionId, StrategyId


class PositionSide(StrEnum):
    LONG = "long"
    SHORT = "short"


class OrderAction(StrEnum):
    BUY = "BUY"
    BUY_TO_COVER = "BUY_TO_COVER"
    SELL = "SELL"
    SELL_SHORT = "SELL_SHORT"


class OrderStatus(StrEnum):
    PENDING = "pending"
    FILLED = "filled"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PortfolioAccount(DomainModel):
    strategy_id: StrategyId
    provider_id: ProviderId
    cash_balance: Decimal = Decimal("0")
    equity_value: Decimal = Decimal("0")
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = Field(default_factory=dict)


class Position(DomainModel):
    id: PositionId
    strategy_id: StrategyId
    provider_id: ProviderId | None
    symbol: Annotated[str, Field(min_length=1)]
    side: str = Field(default=PositionSide.LONG)
    quantity: Decimal
    average_price: Decimal
    opened_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("side")
    @classmethod
    def validate_side(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {PositionSide.LONG.value, PositionSide.SHORT.value}:
            msg = f"Unsupported position side: {value}"
            raise ValueError(msg)
        return normalized


class Order(DomainModel):
    id: OrderId
    strategy_id: StrategyId
    provider_id: ProviderId | None
    symbol: Annotated[str, Field(min_length=1)]
    action: str
    quantity: Decimal
    limit_price: Decimal | None = None
    status: str = OrderStatus.PENDING
    placed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    filled_at: datetime | None = None
    fails_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("action")
    @classmethod
    def normalize_action(cls, value: str) -> str:
        upper = value.upper()
        valid = {action.value for action in OrderAction}
        if upper not in valid:
            msg = f"Unsupported order action: {value}"
            raise ValueError(msg)
        return upper


__all__ = [
    "Order",
    "OrderAction",
    "OrderStatus",
    "PortfolioAccount",
    "Position",
    "PositionSide",
]
