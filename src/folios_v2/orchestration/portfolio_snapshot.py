"""Utilities for gathering provider portfolio context for prompt generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Awaitable, Callable, Iterable

from folios_v2.domain import Order, PortfolioAccount, Position, PositionSide
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.types import StrategyId
from folios_v2.persistence import UnitOfWork


PriceFetcher = Callable[[list[str]], Awaitable[dict[str, Decimal]]]


@dataclass(slots=True)
class PositionSummary:
    """Summary of an open position for inclusion in prompts."""

    symbol: str
    side: str
    quantity: Decimal
    average_price: Decimal
    market_price: Decimal | None = None
    market_value: Decimal | None = None
    unrealized_pl: Decimal | None = None
    unrealized_pl_pct: Decimal | None = None
    weight_pct: Decimal | None = None


@dataclass(slots=True)
class OrderSummary:
    """Minimal representation of a recently filled order."""

    symbol: str
    action: str
    quantity: Decimal
    price: Decimal | None
    filled_at: datetime | None


@dataclass(slots=True)
class PortfolioSnapshot:
    """Aggregate view of a provider's current portfolio."""

    strategy_id: StrategyId
    provider_id: ProviderId
    cash: Decimal
    positions_value: Decimal
    total_value: Decimal
    gross_exposure_pct: Decimal | None
    net_exposure_pct: Decimal | None
    leverage: Decimal | None
    updated_at: datetime | None
    positions: list[PositionSummary] = field(default_factory=list)
    recent_orders: list[OrderSummary] = field(default_factory=list)


def _safe_divide(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return numerator / denominator


async def load_portfolio_snapshot(
    uow: UnitOfWork,
    strategy_id: StrategyId,
    provider_id: ProviderId,
    *,
    price_fetcher: PriceFetcher | None = None,
    recent_order_limit: int = 5,
) -> PortfolioSnapshot | None:
    """Fetch portfolio balances, positions, and recent orders for a provider."""

    account: PortfolioAccount | None = await uow.portfolio_repository.get(
        strategy_id=strategy_id,
        provider_id=provider_id,
    )

    positions: Iterable[Position] = await uow.position_repository.list_open(
        strategy_id,
        provider_id=provider_id,
    )
    positions = list(positions)

    if account is None and not positions:
        return None

    cash_balance = account.cash_balance if account else Decimal("0")
    updated_at = account.updated_at if account else None

    symbols = sorted({pos.symbol for pos in positions})
    prices: dict[str, Decimal] = {}
    if symbols and price_fetcher is not None:
        prices = await price_fetcher(list(symbols))

    position_summaries: list[PositionSummary] = []
    total_market_value = Decimal("0")
    total_abs_market_value = Decimal("0")

    for pos in positions:
        qty = pos.quantity
        avg_price = pos.average_price
        price = prices.get(pos.symbol)

        if price is not None and price > 0:
            market_value = qty * price
            if pos.side == PositionSide.SHORT:
                market_value = -market_value
            unrealized_pl = (price - avg_price) * qty
            if pos.side == PositionSide.SHORT:
                unrealized_pl = (avg_price - price) * qty
        else:
            market_value = None
            unrealized_pl = None

        if market_value is not None:
            total_market_value += market_value
            total_abs_market_value += abs(market_value)

        summary = PositionSummary(
            symbol=pos.symbol,
            side=pos.side,
            quantity=qty,
            average_price=avg_price,
            market_price=price,
            market_value=market_value,
            unrealized_pl=unrealized_pl,
            unrealized_pl_pct=(
                _safe_divide(unrealized_pl, qty * avg_price) * Decimal("100")
                if unrealized_pl is not None and qty * avg_price != 0
                else None
            ),
        )
        position_summaries.append(summary)

    total_value = cash_balance + total_market_value

    gross_exposure_pct: Decimal | None = None
    net_exposure_pct: Decimal | None = None
    leverage: Decimal | None = None

    if total_value != 0:
        gross_exposure_pct = (total_abs_market_value / total_value) * Decimal("100")
        net_exposure_pct = (total_market_value / total_value) * Decimal("100")
        leverage = total_abs_market_value / total_value

        for summary in position_summaries:
            if summary.market_value is not None:
                summary.weight_pct = (
                    summary.market_value / total_value * Decimal("100")
                )

    recent_orders: Iterable[Order] = []
    if recent_order_limit > 0:
        recent_orders = await uow.order_repository.list_recent(
            strategy_id,
            limit=recent_order_limit,
            provider_id=provider_id,
        )
    recent_order_summaries = [
        OrderSummary(
            symbol=order.symbol,
            action=order.action,
            quantity=order.quantity,
            price=order.limit_price,
            filled_at=order.filled_at,
        )
        for order in recent_orders
        if order.status.lower() == "filled"
    ]

    return PortfolioSnapshot(
        strategy_id=strategy_id,
        provider_id=provider_id,
        cash=cash_balance,
        positions_value=total_market_value,
        total_value=total_value,
        gross_exposure_pct=gross_exposure_pct,
        net_exposure_pct=net_exposure_pct,
        leverage=leverage,
        updated_at=updated_at,
        positions=position_summaries,
        recent_orders=recent_order_summaries,
    )


__all__ = [
    "PortfolioSnapshot",
    "PositionSummary",
    "OrderSummary",
    "load_portfolio_snapshot",
]
