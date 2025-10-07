# Portfolio Execution Implementation

## Overview

The portfolio execution engine processes AI research recommendations and converts them into concrete portfolio actions: creating orders, opening/closing positions, and managing portfolio account balances.

## Architecture

### Domain Models

Located in `src/folios_v2/domain/trading.py`:

- **PortfolioAccount**: Tracks cash and equity balances per strategy/provider
- **Position**: Represents an open or closed position in a security
- **Order**: Represents a buy/sell order with execution status

### Repositories

Located in `src/folios_v2/persistence/sqlite/repositories.py`:

- **SQLitePortfolioAccountRepository**: Portfolio account CRUD operations
- **SQLitePositionRepository**: Position management
- **SQLiteOrderRepository**: Order tracking

### Execution Script

Located in `scripts/execute_recommendations.py`:

The execution script performs the following workflow:

1. **Load Recommendations**: Reads `structured.json` or `parsed.json` from artifact directory
2. **Initialize Portfolio Account**: Creates account with initial balance if it doesn't exist
3. **Process Recommendations**: For each recommendation:
   - **BUY**: Calculate position size, create order, create position
   - **HOLD**: Skip (no action)
   - **SELL**: Not yet implemented (requires existing position lookup)
4. **Update Portfolio**: Adjust cash/equity balances
5. **Persist Changes**: Commit all database changes

## Usage

### Basic Execution

```bash
uv run python -m scripts.execute_recommendations \
  <request_id> \
  <strategy_id> \
  --provider-id anthropic \
  --initial-balance 100000 \
  --default-price 450
```

### Parameters

- `request_id`: Research request UUID
- `strategy_id`: Strategy UUID
- `--provider-id`: Provider identifier (anthropic, openai, gemini)
- `--initial-balance`: Initial cash balance (default: $100,000)
- `--default-price`: Default stock price for simulation (default: $100)

### Example

Execute recommendations from Anthropic CLI research request:

```bash
uv run python -m scripts.execute_recommendations \
  79b9930c-3a6f-4f41-ae9b-a3fa8ec37ef2 \
  877be608-8547-4656-9d16-0f395df434dd \
  --provider-id anthropic \
  --initial-balance 100000 \
  --default-price 450
```

**Output:**
```
Using artifact directory: artifacts/79b9930c-3a6f-4f41-ae9b-a3fa8ec37ef2/5f1f84b5-424f-4f6d-a66a-9784bf9e6604
Loaded recommendations from .../structured.json
Found 2 recommendations
Created portfolio account with $100,000.00 initial balance

Processing MSFT: BUY (10.0% allocation)
  Created BUY order: 22.22 shares @ $450.0 = $9,999.00
  Created position: a7ea9754-b424-4314-94c9-92b6165e5059

Processing AAPL: HOLD (6.0% allocation)
  HOLD action - no order created

============================================================
Execution Summary
============================================================
Orders created: 1
Positions created: 1
Total invested: $9,999.00
Remaining cash: $90,001.00
Total equity: $9,999.00
Total portfolio value: $100,000.00
============================================================
```

## Database Verification

### Portfolio Account

```bash
sqlite3 folios_v2.db "
  SELECT
    strategy_id,
    provider_id,
    json_extract(payload, '$.cash_balance') as cash,
    json_extract(payload, '$.equity_value') as equity
  FROM portfolio_accounts
  WHERE strategy_id = '877be608-8547-4656-9d16-0f395df434dd';
"
```

**Result:**
```
877be608-8547-4656-9d16-0f395df434dd|anthropic|90001.000|9999.000
```

### Positions

```bash
sqlite3 folios_v2.db "
  SELECT
    id,
    symbol,
    json_extract(payload, '$.quantity') as qty,
    json_extract(payload, '$.average_price') as price,
    status
  FROM positions
  WHERE strategy_id = '877be608-8547-4656-9d16-0f395df434dd';
"
```

**Result:**
```
a7ea9754-b424-4314-94c9-92b6165e5059|MSFT|22.22|450.0|open
```

### Orders

```bash
sqlite3 folios_v2.db "
  SELECT
    id,
    symbol,
    json_extract(payload, '$.action') as action,
    json_extract(payload, '$.quantity') as qty,
    json_extract(payload, '$.limit_price') as price,
    status
  FROM orders
  WHERE strategy_id = '877be608-8547-4656-9d16-0f395df434dd';
"
```

**Result:**
```
78288a1b-3396-4d18-a03c-fdc3da85a98c|MSFT|BUY|22.22|450.0|filled
```

## Position Sizing Algorithm

Current implementation uses percentage allocation:

```python
allocation_amount = portfolio_value * (allocation_percent / 100)
quantity = (allocation_amount / current_price).quantize(Decimal("0.01"))
```

**Example:**
- Portfolio value: $100,000
- MSFT allocation: 10%
- Price: $450
- Quantity: $10,000 / $450 = 22.22 shares

## Future Enhancements

### 1. SELL Order Implementation

```python
async def _execute_sell_order(
    strategy_id: StrategyId,
    provider_id: ProviderId,
    symbol: str,
    current_price: Decimal,
) -> tuple[Order, Position]:
    # Find existing position
    positions = await uow.position_repository.list_open(strategy_id, provider_id)
    position = next((p for p in positions if p.symbol == symbol), None)

    if position is None:
        raise ValueError(f"No open position for {symbol}")

    # Create sell order
    order = Order(
        id=OrderId(uuid4()),
        strategy_id=strategy_id,
        provider_id=provider_id,
        symbol=symbol,
        action=OrderAction.SELL,
        quantity=position.quantity,
        limit_price=current_price,
        status=OrderStatus.FILLED,
        placed_at=utc_now(),
        filled_at=utc_now(),
    )

    # Close position
    closed_position = position.model_copy(update={"closed_at": utc_now()})

    return order, closed_position
```

### 2. Market Data Integration

Replace `--default-price` with real-time market data:

```python
from folios_v2.market_data import get_current_price

current_price = await get_current_price(symbol)
```

### 3. Position Rebalancing

Calculate target vs. current allocation and generate rebalancing orders:

```python
async def _rebalance_positions(
    strategy_id: StrategyId,
    provider_id: ProviderId,
    target_allocations: dict[str, float],
) -> list[Order]:
    # Get current positions
    positions = await uow.position_repository.list_open(strategy_id, provider_id)

    # Calculate current vs. target allocations
    # Generate buy/sell orders to rebalance
```

### 4. Risk Management

Add position limits and exposure constraints:

```python
MAX_POSITION_SIZE = Decimal("0.20")  # 20% max per position
MAX_SECTOR_EXPOSURE = Decimal("0.40")  # 40% max per sector

def validate_position_limits(allocation_percent: float) -> None:
    if Decimal(str(allocation_percent / 100)) > MAX_POSITION_SIZE:
        raise ValueError(f"Position exceeds max size: {allocation_percent}%")
```

### 5. Execution Tracking

Add metadata for audit trail:

```python
order = Order(
    # ... existing fields
    metadata={
        "request_id": str(request_id),
        "task_id": str(task_id),
        "recommendation_confidence": recommendation.confidence,
        "market_context": recommendation.market_context,
    }
)
```

## Testing

### Unit Tests

Create `tests/test_execute_recommendations.py`:

```python
import pytest
from decimal import Decimal
from uuid import uuid4

from folios_v2.domain import Order, Position, PortfolioAccount
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.types import OrderId, PositionId, StrategyId
from scripts.execute_recommendations import _execute_buy_order

@pytest.mark.asyncio
async def test_execute_buy_order():
    strategy_id = StrategyId(uuid4())
    provider_id = ProviderId.ANTHROPIC

    order, position = await _execute_buy_order(
        strategy_id,
        provider_id,
        "MSFT",
        10.0,  # allocation_percent
        Decimal("100000"),  # portfolio_value
        Decimal("450"),  # current_price
    )

    assert order.symbol == "MSFT"
    assert order.action == "BUY"
    assert order.status == "filled"
    assert position.symbol == "MSFT"
    assert position.quantity == Decimal("22.22")
```

### Integration Tests

Test full workflow with mock database:

```python
@pytest.mark.asyncio
async def test_execute_recommendations_workflow(tmp_path):
    # Create mock artifact directory with structured.json
    # Run execution script
    # Verify database state
```

## Deployment

### Production Considerations

1. **Transaction Safety**: All database operations wrapped in UnitOfWork
2. **Idempotency**: Script can be re-run safely (updates existing positions)
3. **Logging**: All actions logged to stdout for observability
4. **Error Handling**: Graceful failure with rollback on errors

### CI/CD Integration

Add to weekly workflow:

```yaml
- name: Execute Portfolio Recommendations
  run: |
    uv run python -m scripts.execute_recommendations \
      ${{ env.REQUEST_ID }} \
      ${{ env.STRATEGY_ID }} \
      --provider-id anthropic
```

## Changelog

### 2025-10-06 - Initial Implementation

- ✅ Created `scripts/execute_recommendations.py`
- ✅ Implemented BUY order execution
- ✅ Portfolio account initialization
- ✅ Position creation and tracking
- ✅ Database persistence via repositories
- ✅ Tested with Anthropic CLI recommendations
- ⏳ SELL order implementation (pending)
- ⏳ Market data integration (pending)
- ⏳ Position rebalancing (pending)
