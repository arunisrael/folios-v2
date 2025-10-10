"""Portfolio value and P/L computation logic."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Any


class PortfolioEngine:
    """Compute portfolio values, cash balances, and P/L."""

    def compute_cash_balance(
        self,
        initial_capital: Decimal,
        orders: list[dict[str, Any]]
    ) -> Decimal:
        """Compute cash balance from initial capital and filled orders.

        Args:
            initial_capital: Starting cash amount
            orders: List of filled orders with action, quantity, price

        Returns:
            Current cash balance
        """
        cash = initial_capital

        for order in orders:
            action = order.get("action", "")
            quantity = Decimal(str(order.get("quantity", 0)))
            price_val = order.get("price")
            price = Decimal(str(price_val)) if price_val is not None else Decimal("0")

            if action in ("BUY", "BUY_TO_COVER"):
                cash -= quantity * price
            elif action in ("SELL", "SELL_SHORT"):
                cash += quantity * price

        return cash

    def compute_positions_market_value(
        self,
        positions: list[dict[str, Any]],
        prices: dict[str, Decimal]
    ) -> Decimal:
        """Compute total market value of positions.

        Args:
            positions: List of position dicts with symbol, quantity
            prices: Current prices by symbol

        Returns:
            Total market value
        """
        total = Decimal("0")

        for pos in positions:
            symbol = pos.get("symbol", "")
            quantity = Decimal(str(pos.get("quantity", 0)))
            price = prices.get(symbol, Decimal("0"))

            total += quantity * price

        return total

    def compute_unrealized_pl(
        self,
        positions: list[dict[str, Any]],
        prices: dict[str, Decimal]
    ) -> dict[str, Any]:
        """Compute per-position and total unrealized P/L.

        Args:
            positions: List of position dicts with symbol, quantity, avg_entry_price
            prices: Current prices by symbol

        Returns:
            Dict with 'total' and 'by_symbol' unrealized P/L
        """
        total = Decimal("0")
        by_symbol: dict[str, Decimal] = {}

        for pos in positions:
            symbol = pos.get("symbol", "")
            quantity = Decimal(str(pos.get("quantity", 0)))
            avg_entry = pos.get("avg_entry_price")
            current_price = prices.get(symbol, Decimal("0"))

            if avg_entry is not None:
                avg_entry = Decimal(str(avg_entry))
                pl = (current_price - avg_entry) * quantity
                total += pl
                by_symbol[symbol] = pl

        return {"total": total, "by_symbol": by_symbol}

    def compute_realized_pl_from_orders(
        self,
        orders: list[dict[str, Any]]
    ) -> Decimal:
        """Track realized P/L using FIFO inventory accounting.

        Args:
            orders: Chronologically ordered list of filled orders

        Returns:
            Total realized P/L
        """
        inventory: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        realized_pl = Decimal("0")

        for order in orders:
            symbol = order.get("symbol", "")
            action = order.get("action", "")
            quantity = Decimal(str(order.get("quantity", 0)))
            price_val = order.get("price")
            price = Decimal(str(price_val)) if price_val is not None else Decimal("0")

            if action in ("BUY", "BUY_TO_COVER"):
                # Add to inventory
                inventory[symbol].append((quantity, price))

            elif action in ("SELL", "SELL_SHORT"):
                # Remove from inventory (FIFO) and compute P/L
                remaining = quantity
                while remaining > Decimal("0") and inventory[symbol]:
                    lot_qty, lot_price = inventory[symbol][0]

                    if lot_qty <= remaining:
                        # Consume entire lot
                        realized_pl += (price - lot_price) * lot_qty
                        remaining -= lot_qty
                        inventory[symbol].pop(0)
                    else:
                        # Partial lot consumption
                        realized_pl += (price - lot_price) * remaining
                        inventory[symbol][0] = (lot_qty - remaining, lot_price)
                        remaining = Decimal("0")

        return realized_pl

    def build_trade_history(
        self,
        initial_capital: Decimal,
        orders: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, list[tuple[Decimal, Decimal]]]]:
        """Build order-by-order trade history with running balances.

        Args:
            initial_capital: Starting cash amount
            orders: Chronologically ordered list of filled orders

        Returns:
            Tuple of (events, final_inventory) where events contain:
            - timestamp, action, symbol, qty, price
            - cash_delta, cash_balance
            - position_after, realized_pl_delta, realized_pl_total
        """
        events: list[dict[str, Any]] = []
        cash_balance = initial_capital
        inventory: dict[str, list[tuple[Decimal, Decimal]]] = defaultdict(list)
        position_qty: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        realized_pl_total = Decimal("0")

        for order in orders:
            symbol = order.get("symbol", "")
            action = order.get("action", "")
            quantity = Decimal(str(order.get("quantity", 0)))
            price_val = order.get("price")
            price = Decimal(str(price_val)) if price_val is not None else Decimal("0")
            timestamp = order.get("placed_at")

            cash_delta = Decimal("0")
            realized_pl_delta = Decimal("0")

            if action in ("BUY", "BUY_TO_COVER"):
                cash_delta = -(quantity * price)
                cash_balance += cash_delta
                position_qty[symbol] += quantity
                inventory[symbol].append((quantity, price))

            elif action in ("SELL", "SELL_SHORT"):
                cash_delta = quantity * price
                cash_balance += cash_delta
                position_qty[symbol] -= quantity

                # Compute realized P/L (FIFO)
                remaining = quantity
                while remaining > Decimal("0") and inventory[symbol]:
                    lot_qty, lot_price = inventory[symbol][0]

                    if lot_qty <= remaining:
                        realized_pl_delta += (price - lot_price) * lot_qty
                        remaining -= lot_qty
                        inventory[symbol].pop(0)
                    else:
                        realized_pl_delta += (price - lot_price) * remaining
                        inventory[symbol][0] = (lot_qty - remaining, lot_price)
                        remaining = Decimal("0")

                realized_pl_total += realized_pl_delta

            events.append({
                "timestamp": timestamp,
                "action": action,
                "symbol": symbol,
                "quantity": quantity,
                "price": price,
                "cash_delta": cash_delta,
                "cash_balance": cash_balance,
                "position_after": position_qty[symbol],
                "realized_pl_delta": realized_pl_delta,
                "realized_pl_total": realized_pl_total,
                "rationale": order.get("rationale", ""),
            })

        return events, inventory


__all__ = ["PortfolioEngine"]
