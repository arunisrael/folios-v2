"""Test SELL_SHORT order creation for Martin Whitman strategy."""
import asyncio
from decimal import Decimal
from uuid import uuid4

from folios_v2.cli.deps import get_container
from folios_v2.domain import Order, Position
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.trading import OrderAction, OrderStatus, PositionSide
from folios_v2.domain.types import OrderId, PositionId, StrategyId
from folios_v2.market_data import get_current_price
from folios_v2.utils import utc_now


async def main() -> None:
    strategy_id = StrategyId("bb3d4ffe-9511-4c85-9cd8-3d249e476449")
    provider_id = ProviderId.GEMINI
    symbol = "SMCI"

    # Fetch current price
    print(f"Fetching live price for {symbol}...")
    current_price = await get_current_price(symbol)
    print(f"Live price: ${current_price}")

    # Calculate position (3.5% of $100k = $3,500)
    allocation_amount = Decimal("3500")
    quantity = (allocation_amount / current_price).quantize(Decimal("0.01"))

    rationale = (
        "Super Micro's recent quarterly results showed a significant revenue miss "
        "and a lowered full-year forecast, signaling a sharp deceleration in growth. "
        "Compressing gross margins further indicate that the period of exceptional "
        "profitability is waning. The stock appears overvalued as it has not yet "
        "fully priced in this fundamental deterioration and the end of its "
        "hyper-growth phase."
    )

    # Create SELL_SHORT order
    order = Order(
        id=OrderId(uuid4()),
        strategy_id=strategy_id,
        provider_id=provider_id,
        symbol=symbol,
        action=OrderAction.SELL_SHORT,
        quantity=quantity,
        limit_price=current_price,
        status=OrderStatus.FILLED,
        placed_at=utc_now(),
        filled_at=utc_now(),
        metadata={"rationale": rationale},
    )

    # Create short position
    position = Position(
        id=PositionId(uuid4()),
        strategy_id=strategy_id,
        provider_id=provider_id,
        symbol=symbol,
        side=PositionSide.SHORT,
        quantity=quantity,
        average_price=current_price,
        opened_at=utc_now(),
    )

    # Save to database
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        await uow.order_repository.add(order)
        await uow.position_repository.add(position)
        await uow.commit()

    proceeds = order.quantity * order.limit_price
    print(
        f"✓ Created SELL_SHORT order: {order.quantity} shares @ "
        f"${order.limit_price} = ${proceeds:,.2f}"
    )
    print(f"✓ Created short position: {position.id}")
    print(f"✓ Order ID: {order.id}")


if __name__ == "__main__":
    asyncio.run(main())
