from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import List
from uuid import uuid4

import pytest

from folios_v2.domain import Order
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.trading import OrderAction, OrderStatus
from folios_v2.domain.types import OrderId, StrategyId
from folios_v2.utils.order_idempotency import add_order_if_new, build_order_idempotency_key


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class InMemoryOrderRepo:
    orders: List[Order] = field(default_factory=list)

    async def list_recent(self, strategy_id: StrategyId, *, limit: int, provider_id=None) -> List[Order]:
        return [order for order in self.orders if order.strategy_id == strategy_id][:limit]

    async def add(self, order: Order) -> None:
        self.orders.append(order)


def _build_order(quantity: str, price: str) -> Order:
    quantity_dec = Decimal(quantity)
    price_dec = Decimal(price)
    strategy_id = StrategyId(uuid4())
    key = build_order_idempotency_key(
        strategy_id,
        ProviderId.GEMINI,
        "VTI",
        OrderAction.BUY,
        quantity_dec,
        price_dec,
    )
    metadata: dict[str, object] = {"idempotency_key": key}
    return Order(
        id=OrderId(uuid4()),
        strategy_id=strategy_id,
        provider_id=ProviderId.GEMINI,
        symbol="VTI",
        action=OrderAction.BUY,
        quantity=quantity_dec,
        limit_price=price_dec,
        status=OrderStatus.FILLED,
        placed_at=_utc_now(),
        filled_at=_utc_now(),
        metadata=metadata,
    )


@pytest.mark.asyncio
async def test_add_order_if_new_persists_first_order() -> None:
    repo = InMemoryOrderRepo()
    order = _build_order("10", "100")

    added = await add_order_if_new(repo, order)

    assert added is True
    assert len(repo.orders) == 1
    stored_order = repo.orders[0]
    assert stored_order.metadata.get("idempotency_key") == order.metadata.get("idempotency_key")


@pytest.mark.asyncio
async def test_add_order_if_new_detects_duplicate_order() -> None:
    repo = InMemoryOrderRepo()
    order = _build_order("10", "100")
    await repo.add(order)

    # Duplicate order with the same sizing and price
    duplicate = order.model_copy(
        update={
            "id": OrderId(uuid4()),
            "placed_at": order.placed_at + timedelta(seconds=5),
            "filled_at": order.filled_at + timedelta(seconds=5),
            "metadata": order.metadata,
        }
    )

    added = await add_order_if_new(repo, duplicate)

    assert added is False
    assert len(repo.orders) == 1
