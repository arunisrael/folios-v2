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
        inventory: dict[str, list[tuple[Decimal, Decimal, str]]] = defaultdict(list)
        realized_pl = Decimal("0")

        for order in orders:
            symbol = order.get("symbol", "")
            action = order.get("action", "")
            quantity = Decimal(str(order.get("quantity", 0)))
            price_val = order.get("price")
            price = Decimal(str(price_val)) if price_val is not None else Decimal("0")

            if action == "BUY":
                # Add long inventory
                inventory[symbol].append((quantity, price, "long"))

            elif action == "SELL":
                # Remove long inventory (FIFO)
                remaining = quantity
                while remaining > Decimal("0") and inventory[symbol]:
                    lot_qty, lot_price, lot_side = inventory[symbol][0]
                    if lot_side != "long":
                        inventory[symbol].pop(0)
                        continue

                    if lot_qty <= remaining:
                        realized_pl += (price - lot_price) * lot_qty
                        remaining -= lot_qty
                        inventory[symbol].pop(0)
                    else:
                        realized_pl += (price - lot_price) * remaining
                        inventory[symbol][0] = (lot_qty - remaining, lot_price, lot_side)
                        remaining = Decimal("0")

            elif action == "SELL_SHORT":
                # Add short inventory
                inventory[symbol].append((quantity, price, "short"))

            elif action == "BUY_TO_COVER":
                # Remove short inventory (FIFO)
                remaining = quantity
                while remaining > Decimal("0") and inventory[symbol]:
                    lot_qty, lot_price, lot_side = inventory[symbol][0]
                    if lot_side != "short":
                        inventory[symbol].pop(0)
                        continue

                    if lot_qty <= remaining:
                        realized_pl += (lot_price - price) * lot_qty
                        remaining -= lot_qty
                        inventory[symbol].pop(0)
                    else:
                        realized_pl += (lot_price - price) * remaining
                        inventory[symbol][0] = (lot_qty - remaining, lot_price, lot_side)
                        remaining = Decimal("0")

        return realized_pl

    def deduplicate_orders(
        self,
        orders: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Remove duplicate buy orders, keeping only the most recent open lot per symbol.

        Args:
            orders: Filled orders in any sort order.

        Returns:
            Tuple of (deduplicated orders in chronological order, removed duplicate orders).
        """
        if not orders:
            return [], []

        sorted_orders = sorted(orders, key=lambda order: order.get("placed_at") or "")

        deduped: list[dict[str, Any]] = []
        removed: list[dict[str, Any]] = []
        latest_open_index: dict[tuple[str, str], int] = {}

        def action_side(action: str) -> str:
            return "short" if action == "SELL_SHORT" else "long"

        for order in sorted_orders:
            action = (order.get("action") or "").upper()
            symbol = order.get("symbol")

            if not symbol:
                deduped.append(order)
                continue

            if action in {"BUY", "SELL_SHORT"}:
                key = (symbol, action_side(action))
                previous_index = latest_open_index.get(key)
                if previous_index is not None:
                    removed.append(deduped.pop(previous_index))

                    # Re-index existing entries after the removal point.
                    for sym_key, index in list(latest_open_index.items()):
                        if index > previous_index:
                            latest_open_index[sym_key] = index - 1

                latest_open_index[key] = len(deduped)
                deduped.append(order)

            elif action in {"SELL", "BUY_TO_COVER"}:
                deduped.append(order)
                key = (symbol, "long" if action == "SELL" else "short")
                latest_open_index.pop(key, None)

            else:
                deduped.append(order)

        return deduped, removed

    def build_trade_history(
        self,
        initial_capital: Decimal,
        orders: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, list[tuple[Decimal, Decimal, str | None]]]]:
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
        inventory: dict[str, list[tuple[Decimal, Decimal, str, str | None]]] = defaultdict(list)
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

            if action == "BUY":
                cash_delta = -(quantity * price)
                cash_balance += cash_delta
                position_qty[symbol] += quantity
                inventory[symbol].append((quantity, price, "long", timestamp))

            elif action == "SELL":
                cash_delta = quantity * price
                cash_balance += cash_delta
                position_qty[symbol] -= quantity

                # Compute realized P/L (FIFO)
                remaining = quantity
                while remaining > Decimal("0"):
                    lots = [lot for lot in inventory[symbol] if lot[2] == "long"]
                    if not lots:
                        break
                    lot_qty, lot_price, lot_side, lot_timestamp = lots[0]
                    lot_index = inventory[symbol].index(lots[0])

                    if lot_qty <= remaining:
                        realized_pl_delta += (price - lot_price) * lot_qty
                        remaining -= lot_qty
                        inventory[symbol].pop(lot_index)
                    else:
                        realized_pl_delta += (price - lot_price) * remaining
                        inventory[symbol][lot_index] = (lot_qty - remaining, lot_price, lot_side, lot_timestamp)
                        remaining = Decimal("0")

                realized_pl_total += realized_pl_delta

            elif action == "SELL_SHORT":
                cash_delta = quantity * price
                cash_balance += cash_delta
                position_qty[symbol] -= quantity
                inventory[symbol].append((quantity, price, "short", timestamp))

            elif action == "BUY_TO_COVER":
                cash_delta = -(quantity * price)
                cash_balance += cash_delta
                position_qty[symbol] += quantity

                remaining = quantity
                while remaining > Decimal("0"):
                    lots = [lot for lot in inventory[symbol] if lot[2] == "short"]
                    if not lots:
                        break
                    lot_qty, lot_price, lot_side, lot_timestamp = lots[0]
                    lot_index = inventory[symbol].index(lots[0])

                    if lot_qty <= remaining:
                        realized_pl_delta += (lot_price - price) * lot_qty
                        remaining -= lot_qty
                        inventory[symbol].pop(lot_index)
                    else:
                        realized_pl_delta += (lot_price - price) * remaining
                        inventory[symbol][lot_index] = (lot_qty - remaining, lot_price, lot_side, lot_timestamp)
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

    def summarize_inventory(
        self,
        inventory: dict[str, list[tuple[Decimal, Decimal, str, str | None]]]
    ) -> list[dict[str, Any]]:
        """Convert remaining inventory lots into aggregate open positions.

        Args:
            inventory: Mapping of symbol to remaining lots (quantity, price, timestamp).

        Returns:
            List of position dictionaries suitable for reporting.
        """
        positions: list[dict[str, Any]] = []

        for symbol, lots in inventory.items():
            grouped: dict[str, list[tuple[Decimal, Decimal, str | None]]] = defaultdict(list)
            for qty, price, side, ts in lots:
                grouped[side].append((qty, price, ts))

            for side, side_lots in grouped.items():
                total_qty = sum((qty for qty, _price, _ts in side_lots), start=Decimal("0"))
                if total_qty == 0:
                    continue

                total_cost = sum((qty * price for qty, price, _ts in side_lots), start=Decimal("0"))
                avg_price = total_cost / total_qty if total_qty != 0 else Decimal("0")

                opened_at = None
                for _qty, _price, lot_ts in side_lots:
                    if lot_ts is None:
                        continue
                    lot_ts_str = str(lot_ts)
                    if opened_at is None or lot_ts_str < str(opened_at):
                        opened_at = lot_ts

                positions.append({
                    "symbol": symbol,
                    "side": side,
                    "quantity": total_qty.copy_abs(),
                    "avg_entry_price": avg_price.copy_abs(),
                    "opened_at": opened_at,
                    "closed_at": None,
                })

        positions.sort(key=lambda pos: pos["symbol"])
        return positions


__all__ = ["PortfolioEngine"]
