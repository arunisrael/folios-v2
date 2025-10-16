"""Data loading utilities for HTML generation."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine


class HTMLDataLoader:
    """Centralized data access for HTML generation."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def load_strategies(self) -> list[dict[str, Any]]:
        """Load all strategies with their payloads.

        Returns:
            List of strategy dicts with id, name, status, and payload fields.
        """
        import json

        query = text("""
            SELECT id, name, status, payload
            FROM strategies
            ORDER BY name
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query)
            strategies = []
            for row in result:
                payload = row.payload
                if isinstance(payload, str):
                    payload = json.loads(payload) if payload else {}
                elif payload is None:
                    payload = {}

                strategies.append({
                    "id": row.id,
                    "name": row.name,
                    "status": row.status,
                    "payload": payload,
                })
            return strategies

    def load_portfolio_accounts(self, strategy_id: str) -> list[dict[str, Any]]:
        """Load provider-scoped portfolio accounts for a strategy.

        Args:
            strategy_id: The strategy ID

        Returns:
            List of portfolio account dicts with provider_id and payload fields.
        """
        import json

        query = text("""
            SELECT id, strategy_id, provider_id, payload
            FROM portfolio_accounts
            WHERE strategy_id = :strategy_id
            ORDER BY provider_id
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, {"strategy_id": strategy_id})
            accounts = []
            for row in result:
                payload = row.payload
                if isinstance(payload, str):
                    payload = json.loads(payload) if payload else {}
                elif payload is None:
                    payload = {}

                updated_at = payload.get("updated_at")
                if updated_at:
                    if isinstance(updated_at, str):
                        try:
                            updated_at_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                        except ValueError:
                            updated_at_dt = None
                    else:
                        updated_at_dt = updated_at
                else:
                    updated_at_dt = None

                accounts.append({
                    "id": row.id,
                    "strategy_id": row.strategy_id,
                    "provider_id": row.provider_id,
                    "cash_balance": payload.get("cash_balance", 0),
                    "equity_value": payload.get("equity_value", 0),
                    "updated_at": updated_at_dt,
                    "payload": payload,
                })
            return accounts

    def load_positions(
        self,
        strategy_id: str,
        provider_id: str | None = None,
        status: str = "open"
    ) -> list[dict[str, Any]]:
        """Load positions for a strategy, optionally filtered by provider.

        Args:
            strategy_id: The strategy ID
            provider_id: Optional provider filter
            status: Position status (default: "open")

        Returns:
            List of position dicts with extracted payload fields.
        """
        if provider_id is not None:
            query = text("""
                SELECT id, strategy_id, provider_id, symbol, status,
                       opened_at, closed_at, payload
                FROM positions
                WHERE strategy_id = :strategy_id
                  AND provider_id = :provider_id
                  AND status = :status
                ORDER BY opened_at DESC
            """)
            params = {
                "strategy_id": strategy_id,
                "provider_id": provider_id,
                "status": status
            }
        else:
            query = text("""
                SELECT id, strategy_id, provider_id, symbol, status,
                       opened_at, closed_at, payload
                FROM positions
                WHERE strategy_id = :strategy_id
                  AND status = :status
                ORDER BY opened_at DESC
            """)
            params = {"strategy_id": strategy_id, "status": status}

        with self.engine.connect() as conn:
            result = conn.execute(query, params)
            positions = []
            for row in result:
                positions.append(self._extract_position_data(row))
            return positions

    def load_orders(
        self,
        strategy_id: str | None = None,
        provider_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        status: str = "filled"
    ) -> list[dict[str, Any]]:
        """Load orders with optional filters.

        Args:
            strategy_id: Optional strategy filter
            provider_id: Optional provider filter
            since: Optional start date filter
            until: Optional end date filter
            status: Order status (default: "filled")

        Returns:
            List of order dicts with extracted payload fields.
        """
        conditions = ["status = :status"]
        params: dict[str, Any] = {"status": status}

        if strategy_id is not None:
            conditions.append("strategy_id = :strategy_id")
            params["strategy_id"] = strategy_id

        if provider_id is not None:
            conditions.append("provider_id = :provider_id")
            params["provider_id"] = provider_id

        if since is not None:
            conditions.append("placed_at >= :since")
            params["since"] = since

        if until is not None:
            conditions.append("placed_at <= :until")
            params["until"] = until

        where_clause = " AND ".join(conditions)
        query = text(f"""
            SELECT id, strategy_id, provider_id, status, symbol, placed_at, payload
            FROM orders
            WHERE {where_clause}
            ORDER BY placed_at DESC
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, params)
            orders = []
            for row in result:
                orders.append(self._extract_order_data(row))
            return orders

    def load_recent_orders(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Load recent orders for activity feed.

        Args:
            limit: Maximum number of orders to return

        Returns:
            List of recent order dicts.
        """
        query = text("""
            SELECT id, strategy_id, provider_id, status, symbol, placed_at, payload
            FROM orders
            WHERE status = 'filled'
            ORDER BY placed_at DESC
            LIMIT :limit
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, {"limit": limit})
            orders = []
            for row in result:
                orders.append(self._extract_order_data(row))
            return orders

    def get_position_snapshot(
        self,
        strategy_id: str,
        as_of: datetime | str
    ) -> dict[str, float]:
        """Get position quantities as of a specific date.

        This reconstructs position quantities by looking at all orders
        up to the given date.

        Args:
            strategy_id: The strategy ID
            as_of: Date to snapshot at (datetime or ISO string)

        Returns:
            Dict mapping symbol -> quantity
        """
        import json

        if isinstance(as_of, str):
            as_of_param = as_of
        else:
            as_of_param = as_of.isoformat()

        query = text("""
            SELECT symbol, payload
            FROM orders
            WHERE strategy_id = :strategy_id
              AND status = 'filled'
              AND placed_at <= :as_of
            ORDER BY placed_at
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query, {
                "strategy_id": strategy_id,
                "as_of": as_of_param
            })

            # Reconstruct positions from order history
            positions: dict[str, float] = {}
            for row in result:
                payload = row.payload
                if isinstance(payload, str):
                    payload = json.loads(payload) if payload else {}
                elif payload is None:
                    payload = {}

                symbol = row.symbol
                action = payload.get("action", "")
                quantity = float(payload.get("quantity", 0))

                if symbol not in positions:
                    positions[symbol] = 0.0

                if action in ("BUY", "BUY_TO_COVER"):
                    positions[symbol] += quantity
                elif action in ("SELL", "SELL_SHORT"):
                    positions[symbol] -= quantity

            # Remove zero/closed positions
            return {sym: qty for sym, qty in positions.items() if abs(qty) > 0.001}

    def _extract_position_data(self, row: Any) -> dict[str, Any]:
        """Extract position data from database row.

        Args:
            row: Database row from positions table

        Returns:
            Dict with merged column + payload fields
        """
        import json

        payload = row.payload
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        elif payload is None:
            payload = {}

        return {
            "id": row.id,
            "strategy_id": row.strategy_id,
            "provider_id": row.provider_id,
            "symbol": row.symbol,
            "status": row.status,
            "opened_at": row.opened_at,
            "closed_at": row.closed_at,
            "side": payload.get("side", "long"),  # long or short
            "quantity": payload.get("quantity", 0),
            "avg_entry_price": payload.get("average_price"),  # Note: stored as "average_price" in DB
            "payload": payload,
        }

    def _extract_order_data(self, row: Any) -> dict[str, Any]:
        """Extract order data from database row.

        Args:
            row: Database row from orders table

        Returns:
            Dict with merged column + payload fields
        """
        import json

        payload = row.payload
        if isinstance(payload, str):
            payload = json.loads(payload) if payload else {}
        elif payload is None:
            payload = {}

        # Extract rationale from metadata if it exists
        metadata = payload.get("metadata", {})
        if isinstance(metadata, str):
            import json
            try:
                metadata = json.loads(metadata) if metadata else {}
            except Exception:
                metadata = {}

        rationale = metadata.get("rationale", "") if isinstance(metadata, dict) else ""

        return {
            "id": row.id,
            "strategy_id": row.strategy_id,
            "provider_id": row.provider_id,
            "symbol": row.symbol,
            "status": row.status,
            "placed_at": row.placed_at,
            "action": payload.get("action"),  # BUY, SELL, etc.
            "quantity": payload.get("quantity", 0),
            "price": payload.get("limit_price"),  # Price is stored as limit_price
            "rationale": rationale,
            "payload": payload,
        }

    def load_all_strategy_provider_pairs(self) -> list[tuple[str, str]]:
        """Load all unique strategy+provider combinations that have requests or portfolio accounts.

        Returns:
            List of (strategy_id, provider_id) tuples
        """
        query = text("""
            SELECT DISTINCT strategy_id, provider_id
            FROM (
                SELECT strategy_id, provider_id FROM requests WHERE provider_id IS NOT NULL
                UNION
                SELECT strategy_id, provider_id FROM portfolio_accounts WHERE provider_id IS NOT NULL
            )
            ORDER BY strategy_id, provider_id
        """)

        with self.engine.connect() as conn:
            result = conn.execute(query)
            return [(row.strategy_id, row.provider_id) for row in result]


__all__ = ["HTMLDataLoader"]
