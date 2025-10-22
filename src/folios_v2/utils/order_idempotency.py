"""Helpers for detecting and preventing duplicate portfolio orders."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from hashlib import sha256
from typing import Protocol

from folios_v2.domain import Order
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.types import StrategyId


class SupportsOrderLookup(Protocol):
    async def list_recent(
        self,
        strategy_id: StrategyId,
        *,
        limit: int,
        provider_id: ProviderId | None = None,
    ) -> list[Order]:
        ...


@dataclass(frozen=True)
class OrderFingerprint:
    """Unique signature for an order based on sizing and economics."""

    strategy_id: StrategyId
    provider_id: ProviderId | None
    symbol: str
    action: str
    quantity: Decimal
    limit_price: Decimal | None

    def key(self) -> str:
        provider_value = self.provider_id.value if self.provider_id else "default"
        qty_str = f"{self.quantity.normalize():f}"
        price_str = (
            f"{self.limit_price.normalize():f}"
            if isinstance(self.limit_price, Decimal)
            else "None"
        )
        payload = "::".join(
            (
                str(self.strategy_id),
                provider_value,
                self.symbol.upper(),
                self.action.upper(),
                qty_str,
                price_str,
            )
        )
        digest = sha256(payload.encode("utf-8", errors="ignore")).hexdigest()
        return digest


def build_order_fingerprint(order: Order) -> OrderFingerprint:
    """Create a fingerprint representation for an order."""
    limit_price = order.limit_price if isinstance(order.limit_price, Decimal) else None
    return OrderFingerprint(
        strategy_id=order.strategy_id,
        provider_id=order.provider_id,
        symbol=order.symbol,
        action=order.action,
        quantity=order.quantity,
        limit_price=limit_price,
    )


def build_order_idempotency_key(
    strategy_id: StrategyId,
    provider_id: ProviderId | None,
    symbol: str,
    action: str,
    quantity: Decimal,
    limit_price: Decimal | None,
) -> str:
    """Compute an idempotency key without requiring an Order instance."""
    fingerprint = OrderFingerprint(
        strategy_id=strategy_id,
        provider_id=provider_id,
        symbol=symbol,
        action=action,
        quantity=quantity,
        limit_price=limit_price,
    )
    return fingerprint.key()


async def is_duplicate_order(
    repository: SupportsOrderLookup,
    order: Order,
    *,
    recent_limit: int = 250,
    quantity_tolerance: Decimal = Decimal("0.001"),
    price_tolerance: Decimal = Decimal("0.01"),
    lookback_cutoff: datetime | None = None,
) -> bool:
    """Return True when an equivalent order already exists."""
    fingerprint = build_order_fingerprint(order)
    target_key = fingerprint.key()

    recent_orders = await repository.list_recent(
        order.strategy_id,
        limit=recent_limit,
        provider_id=order.provider_id,
    )

    for existing in recent_orders:
        if lookback_cutoff and existing.placed_at and existing.placed_at < lookback_cutoff:
            # Skip orders older than the lookback threshold, if provided.
            continue

        existing_meta = existing.metadata if isinstance(existing.metadata, dict) else {}
        existing_key = existing_meta.get("idempotency_key")
        if existing_key and existing_key == target_key:
            return True

        if existing.action != order.action or existing.symbol.upper() != order.symbol.upper():
            continue

        qty_diff = (existing.quantity - order.quantity).copy_abs()
        if qty_diff > quantity_tolerance:
            continue

        existing_price = (
            existing.limit_price if isinstance(existing.limit_price, Decimal) else None
        )
        candidate_price = (
            order.limit_price if isinstance(order.limit_price, Decimal) else None
        )

        if existing_price is None and candidate_price is None:
            return True

        if existing_price is None or candidate_price is None:
            continue

        price_diff = (existing_price - candidate_price).copy_abs()
        if price_diff <= price_tolerance:
            return True

    return False


async def add_order_if_new(
    repository: SupportsOrderLookup,
    order: Order,
    *,
    recent_limit: int = 250,
    quantity_tolerance: Decimal = Decimal("0.001"),
    price_tolerance: Decimal = Decimal("0.01"),
    lookback_cutoff: datetime | None = None,
) -> bool:
    """Persist an order only when it is not a duplicate.

    Returns:
        True if the order was persisted, False if it was considered a duplicate.
    """
    metadata = order.metadata if isinstance(order.metadata, dict) else {}
    fingerprint = build_order_fingerprint(order)
    idempotency_key = metadata.get("idempotency_key", fingerprint.key())

    duplicate = await is_duplicate_order(
        repository,
        order,
        recent_limit=recent_limit,
        quantity_tolerance=quantity_tolerance,
        price_tolerance=price_tolerance,
        lookback_cutoff=lookback_cutoff,
    )
    if duplicate:
        return False

    if isinstance(order.metadata, dict) and "idempotency_key" not in order.metadata:
        # Persist a copy with the computed idempotency key to maintain future deduping.
        order = order.model_copy(
            update={
                "metadata": {**order.metadata, "idempotency_key": idempotency_key},
            }
        )
    await repository.add(order)
    return True


__all__ = [
    "OrderFingerprint",
    "add_order_if_new",
    "build_order_fingerprint",
    "build_order_idempotency_key",
    "is_duplicate_order",
]
