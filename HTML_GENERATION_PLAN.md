# HTML Generation Implementation Plan for Folios-v2

## Overview

This document outlines the implementation plan for generating static HTML files in folios-v2, based on the proven approach from folios-py. The system will generate four types of HTML outputs:

1. **Leaderboard** (`public/index.html`) - Strategy performance rankings
2. **Activity Feed** (`public/feed.html`) - Recent trading activity
3. **Detailed Strategy Views** (`public/strategy-{strategy_id}.html`) - Per-strategy breakdowns
4. **Weekly Email Summary** (`public/email/week-{date}.html`) - Digest emails

## Source Analysis: folios-py HTML Generation

### Key Scripts Reviewed

#### 1. `scripts/generate_public_html.py` (1,264 lines)
**Purpose:** Main HTML generator for leaderboard, strategy details, and activity feed

**Key Features:**
- Async price fetching from Yahoo Finance with fallback to DB cache
- Provider-scoped portfolio tracking (multiple providers per strategy)
- Real-time portfolio value computation (positions + cash)
- Trade history with P/L tracking
- Batch price fetching (40 symbols at a time, 45s timeout)
- Recomputes and persists provider portfolio snapshots before rendering

**Data Sources:**
- `strategies` table - strategy definitions
- `strategy_provider_portfolios` table - provider-scoped portfolio snapshots
- `positions` table - current positions (with provider column)
- `orders` table - filled orders for cash/P&L computation
- `quotes`/`ohlcv` tables - market price fallbacks

**Output Files:**
- `public/index.html` - Leaderboard sorted by return %
- `public/strategy-{id}.html` - Strategy detail pages
- `public/feed.html` - Activity feed grouped by date

**HTML Styling:** Inline CSS using -apple-system font stack, simple table layouts, responsive design

#### 2. `scripts/generate_weekly_email.py` (902 lines)
**Purpose:** Weekly digest email generation

**Key Features:**
- Date range filtering (default: last 7 days)
- Position snapshot comparison (start vs end of week)
- Popular holdings tracking (count + dollar-weighted %)
- New ticker analysis (most bought/sold)
- Per-strategy activity summaries with rationale
- Optional AI narrative summary (OpenAI/Gemini)

**Data Analysis:**
- Opened/closed positions delta
- Add/trim analysis for continuing positions
- Order aggregation with rationale grouping
- Dollar-weighted exposure calculations

**Output Files:**
- `public/email/week-{date}.html`
- `public/email/latest.html` (symlink/copy)

**Email Design:** Professional email-optimized HTML with inline styles, responsive tables, 640px max-width

## folios-v2 Database Schema Mapping

### Available Tables (from `persistence/sqlite/models.py`)

```python
StrategyRecord              → strategies table (id, name, status, payload)
StrategyScheduleRecord      → strategy_schedules
StrategyRunRecord          → strategy_runs (id, strategy_id, iso_year, iso_week, status)
RequestRecord              → requests (lifecycle tracking)
ExecutionTaskRecord        → execution_tasks
EmailDigestRecord          → email_digests (for weekly emails)
PositionSnapshotRecord     → position_snapshots (Monday snapshots)
PositionRecord             → positions (id, strategy_id, provider_id, symbol, status, opened_at, closed_at)
OrderRecord                → orders (id, strategy_id, provider_id, status, symbol, placed_at)
PortfolioAccountRecord     → portfolio_accounts (strategy_id, provider_id, cash/equity)
RequestLogRecord           → request_logs (state transitions)
```

### Key Differences from folios-py

1. **Provider Tracking**: Uses `provider_id` column (ProviderId enum) instead of string "provider"
2. **JSON Payloads**: Uses `payload` column for extensible data storage
3. **Type Safety**: Strict typing with Pydantic models in `domain/` layer
4. **Portfolio State**: Has dedicated `portfolio_accounts` table with cash_balance and equity_value
5. **Request Lifecycle**: Formal request/task tracking system (not present in folios-py)

## Implementation Plan

### Phase 1: Core Data Access Layer

**File:** `scripts/html/data_loader.py`

```python
"""Data loading utilities for HTML generation."""

from typing import Any
from sqlalchemy.engine import Engine
from datetime import datetime

class HTMLDataLoader:
    """Centralized data access for HTML generation."""

    def __init__(self, engine: Engine):
        self.engine = engine

    def load_strategies(self) -> list[dict[str, Any]]:
        """Load all strategies with their payloads."""

    def load_portfolio_accounts(self, strategy_id: str) -> list[dict[str, Any]]:
        """Load provider-scoped portfolio accounts for a strategy."""

    def load_positions(
        self,
        strategy_id: str,
        provider_id: str | None = None,
        status: str = "open"
    ) -> list[dict[str, Any]]:
        """Load positions for a strategy, optionally filtered by provider."""

    def load_orders(
        self,
        strategy_id: str | None = None,
        provider_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        status: str = "filled"
    ) -> list[dict[str, Any]]:
        """Load orders with optional filters."""

    def load_recent_orders(self, limit: int = 1000) -> list[dict[str, Any]]:
        """Load recent orders for activity feed."""

    def get_position_snapshot(
        self,
        strategy_id: str,
        as_of: datetime
    ) -> dict[str, float]:
        """Get position quantities as of a specific date."""
```

### Phase 2: Portfolio Computation Engine

**File:** `scripts/html/portfolio_engine.py`

```python
"""Portfolio value and P/L computation logic."""

from decimal import Decimal
from typing import Any

class PortfolioEngine:
    """Compute portfolio values, cash balances, and P/L."""

    def compute_cash_balance(
        self,
        strategy_id: str,
        provider_id: str | None,
        initial_capital: Decimal,
        orders: list[dict[str, Any]]
    ) -> Decimal:
        """Compute cash balance from initial capital and filled orders."""

    def compute_positions_market_value(
        self,
        positions: list[dict[str, Any]],
        prices: dict[str, float]
    ) -> Decimal:
        """Compute total market value of positions."""

    def compute_unrealized_pl(
        self,
        positions: list[dict[str, Any]],
        prices: dict[str, float]
    ) -> dict[str, Decimal]:
        """Compute per-position and total unrealized P/L."""

    def compute_realized_pl_from_orders(
        self,
        orders: list[dict[str, Any]]
    ) -> Decimal:
        """Track realized P/L using FIFO inventory accounting."""

    def build_trade_history(
        self,
        initial_capital: Decimal,
        orders: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:
        """Build order-by-order trade history with running balances.

        Returns:
            (events, final_inventory) where events contain:
            - timestamp, action, symbol, qty, price
            - cash_delta, cash_balance
            - position_after, realized_pl_delta, realized_pl_total
        """
```

### Phase 3: Market Data Service

**File:** `scripts/html/market_data.py`

```python
"""Market data fetching with caching."""

import asyncio
from typing import Sequence

class MarketDataService:
    """Fetch live prices with database fallback."""

    def __init__(self, engine: Engine):
        self.engine = engine
        # Consider reusing folios_v2.screeners.providers.* if available

    async def get_current_prices(
        self,
        symbols: Sequence[str],
        chunk_size: int = 40,
        timeout: float = 45.0
    ) -> dict[str, float | None]:
        """Batch fetch current prices from Yahoo Finance.

        Falls back to database quotes/ohlcv on timeout/error.
        """

    async def get_latest_price_from_db(self, symbol: str) -> float | None:
        """Get latest price from quotes or ohlcv tables."""
```

**Note:** Check if `folios_v2.screeners.providers.fmp` or similar can provide price data

### Phase 4: HTML Rendering Templates

**File:** `scripts/html/templates.py`

```python
"""HTML template rendering functions."""

from typing import Any
import html

def base_css() -> str:
    """Return base CSS styles (copy from folios-py)."""

def render_html_page(title: str, body_html: str) -> str:
    """Wrap body in full HTML document with meta tags."""

def render_leaderboard(
    strategies: list[dict[str, Any]],
    portfolio_accounts: dict[str, list[dict[str, Any]]]
) -> str:
    """Render leaderboard HTML (index.html)."""

def render_strategy_detail(
    strategy: dict[str, Any],
    portfolio_accounts: list[dict[str, Any]],
    positions_by_provider: dict[str | None, list[dict[str, Any]]],
    trade_history_by_provider: dict[str | None, list[dict[str, Any]]]
) -> str:
    """Render strategy detail page."""

def render_activity_feed(
    orders: list[dict[str, Any]],
    strategy_id_to_name: dict[str, str]
) -> str:
    """Render activity feed grouped by date."""

# Email-specific templates

def render_weekly_email(
    title: str,
    hero_text: str,
    sections: list[tuple[str, str]],
    generated_at: datetime
) -> str:
    """Render email-optimized HTML with inline styles."""
```

### Phase 5: Main Generation Scripts

#### File: `scripts/generate_public_html.py`

```python
"""Generate static HTML pages for strategies and portfolios.

Outputs to public/:
- index.html: Leaderboard
- strategy-{id}.html: Per-strategy details
- feed.html: Activity feed

Usage:
    python -m scripts.generate_public_html --db folios_v2.db --out public/
"""

import argparse
import asyncio
from pathlib import Path
from sqlalchemy import create_engine

from scripts.html.data_loader import HTMLDataLoader
from scripts.html.market_data import MarketDataService
from scripts.html.portfolio_engine import PortfolioEngine
from scripts.html.templates import (
    render_leaderboard,
    render_strategy_detail,
    render_activity_feed,
    render_html_page
)

async def main():
    parser = argparse.ArgumentParser(description="Generate public HTML")
    parser.add_argument("--db", default="folios_v2.db")
    parser.add_argument("--out", default="public")
    args = parser.parse_args()

    # Setup
    engine = create_engine(f"sqlite:///{args.db}")
    loader = HTMLDataLoader(engine)
    market_svc = MarketDataService(engine)
    portfolio_engine = PortfolioEngine()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load all strategies
    strategies = loader.load_strategies()

    # Collect all symbols for batch price fetch
    all_symbols: set[str] = set()
    for strategy in strategies:
        sid = strategy["id"]
        positions = loader.load_positions(sid, status="open")
        for pos in positions:
            all_symbols.add(pos["symbol"])

    # Batch fetch prices
    print(f"Fetching prices for {len(all_symbols)} symbols...")
    prices = await market_svc.get_current_prices(sorted(all_symbols))

    # Build portfolio data for each strategy
    portfolio_accounts_by_strategy: dict[str, list[dict]] = {}
    positions_by_strategy: dict[str, dict[str | None, list[dict]]] = {}
    trade_history_by_strategy: dict[str, dict[str | None, list[dict]]] = {}

    for strategy in strategies:
        sid = strategy["id"]

        # Load portfolio accounts (provider-scoped)
        accounts = loader.load_portfolio_accounts(sid)
        portfolio_accounts_by_strategy[sid] = accounts

        # Get unique providers (from accounts + positions)
        providers: set[str | None] = {acc["provider_id"] for acc in accounts}
        positions = loader.load_positions(sid, status="open")
        providers.update(pos.get("provider_id") for pos in positions)

        if not providers:
            providers.add(None)  # legacy unscoped

        # Per-provider breakdown
        positions_by_provider: dict[str | None, list[dict]] = {}
        trade_history_by_provider: dict[str | None, list[dict]] = {}

        for provider_id in providers:
            pos = loader.load_positions(sid, provider_id=provider_id, status="open")
            positions_by_provider[provider_id] = pos

            orders = loader.load_orders(sid, provider_id=provider_id, status="filled")
            events, inventory = portfolio_engine.build_trade_history(
                initial_capital=Decimal(strategy.get("initial_capital_usd", 100000)),
                orders=orders
            )
            trade_history_by_provider[provider_id] = events

        positions_by_strategy[sid] = positions_by_provider
        trade_history_by_strategy[sid] = trade_history_by_provider

    # Render leaderboard
    index_html = render_leaderboard(strategies, portfolio_accounts_by_strategy)
    (out_dir / "index.html").write_text(index_html, encoding="utf-8")

    # Render per-strategy pages
    for strategy in strategies:
        sid = strategy["id"]
        detail_html = render_strategy_detail(
            strategy,
            portfolio_accounts_by_strategy[sid],
            positions_by_strategy[sid],
            trade_history_by_strategy[sid]
        )
        (out_dir / f"strategy-{sid}.html").write_text(detail_html, encoding="utf-8")

    # Render activity feed
    recent_orders = loader.load_recent_orders(limit=2000)
    strategy_map = {s["id"]: s["name"] for s in strategies}
    feed_html = render_activity_feed(recent_orders, strategy_map)
    (out_dir / "feed.html").write_text(feed_html, encoding="utf-8")

    print(f"Generated {len(strategies)} strategy pages + index.html + feed.html")

if __name__ == "__main__":
    asyncio.run(main())
```

#### File: `scripts/generate_weekly_email.py`

```python
"""Generate weekly email digest HTML.

Outputs to public/email/:
- week-{date}.html
- latest.html

Usage:
    python -m scripts.generate_weekly_email \
        --db folios_v2.db \
        --out public/email \
        --since 2025-10-01 \
        --until 2025-10-08
"""

import argparse
import asyncio
from pathlib import Path
from datetime import datetime, timedelta
from collections import Counter, defaultdict

from scripts.html.data_loader import HTMLDataLoader
from scripts.html.market_data import MarketDataService
from scripts.html.templates import render_weekly_email

async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="folios_v2.db")
    parser.add_argument("--out", default="public/email")
    parser.add_argument("--since", default=None, help="YYYY-MM-DD")
    parser.add_argument("--until", default=None, help="YYYY-MM-DD")
    args = parser.parse_args()

    # Date range (default: last 7 days)
    until = args.until or datetime.utcnow().date().isoformat()
    since = args.since or (datetime.utcnow().date() - timedelta(days=7)).isoformat()

    engine = create_engine(f"sqlite:///{args.db}")
    loader = HTMLDataLoader(engine)
    market_svc = MarketDataService(engine)

    strategies = loader.load_strategies()
    id_to_name = {s["id"]: s["name"] for s in strategies}

    # Load weekly orders
    orders = loader.load_orders(since=since, until=until, status="filled")

    # Build start/end snapshots for position delta
    start_snaps: dict[str, dict[str, float]] = {}
    end_snaps: dict[str, dict[str, float]] = {}
    all_symbols: set[str] = set()

    for strategy in strategies:
        sid = strategy["id"]
        start_snap = loader.get_position_snapshot(sid, as_of=since)
        end_snap = loader.get_position_snapshot(sid, as_of=until)
        start_snaps[sid] = start_snap
        end_snaps[sid] = end_snap
        all_symbols.update(start_snap.keys())
        all_symbols.update(end_snap.keys())

    # Fetch prices
    prices = await market_svc.get_current_prices(sorted(all_symbols))

    # Aggregate weekly activity
    total_buys = sum(1 for o in orders if o["action"] in ("BUY", "BUY_TO_COVER"))
    total_sells = sum(1 for o in orders if o["action"] in ("SELL", "SELL_SHORT"))
    opened_count = sum(
        len(set(end_snaps[s["id"]].keys()) - set(start_snaps[s["id"]].keys()))
        for s in strategies
    )
    closed_count = sum(
        len(set(start_snaps[s["id"]].keys()) - set(end_snaps[s["id"]].keys()))
        for s in strategies
    )

    # Popular holdings (from end snapshots)
    popular_counts: Counter[str] = Counter()
    for sid, pos in end_snaps.items():
        for sym, qty in pos.items():
            if qty > 0:
                popular_counts[sym] += 1

    # Build email sections
    hero_text = (
        f"Across {len(strategies)} strategies, {total_buys} buys and {total_sells} sells. "
        f"{opened_count} positions opened, {closed_count} closed."
    )

    sections: list[tuple[str, str]] = [
        ("Popular Holdings", _render_popular_holdings_html(popular_counts, prices)),
        ("Weekly Activity", _render_weekly_activity_html(orders, id_to_name)),
        # Add more sections as needed
    ]

    html_out = render_weekly_email(
        title=f"Weekly Strategy Digest ({since} → {until})",
        hero_text=hero_text,
        sections=sections,
        generated_at=datetime.utcnow()
    )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    (out_dir / f"week-{until}.html").write_text(html_out, encoding="utf-8")
    (out_dir / "latest.html").write_text(html_out, encoding="utf-8")

    print(f"Generated {out_dir / f'week-{until}.html'}")

if __name__ == "__main__":
    asyncio.run(main())
```

### Phase 6: Integration with Makefile

Add to `folios-v2/Makefile`:

```makefile
.PHONY: generate-html
generate-html: ## Generate public HTML files (leaderboard, strategies, feed)
	python -m scripts.generate_public_html --db $(FOLIOS_DB) --out public/

.PHONY: generate-email
generate-email: ## Generate weekly email digest
	python -m scripts.generate_weekly_email --db $(FOLIOS_DB) --out public/email

.PHONY: publish-html
publish-html: generate-html generate-email ## Generate all HTML outputs
	@echo "HTML files generated in public/"
```

## Implementation Checklist

### Core Infrastructure
- [ ] Create `scripts/html/` directory structure
- [ ] Implement `data_loader.py` with SQLAlchemy queries
- [ ] Implement `portfolio_engine.py` with Decimal-based math
- [ ] Implement `market_data.py` with async price fetching
- [ ] Port CSS and base template from `folios-py/scripts/generate_public_html.py`

### HTML Renderers
- [ ] Implement `templates.py` with all rendering functions
- [ ] Copy and adapt leaderboard rendering logic
- [ ] Copy and adapt strategy detail page logic
- [ ] Copy and adapt activity feed logic
- [ ] Copy and adapt email digest logic

### Main Scripts
- [ ] Create `scripts/generate_public_html.py`
- [ ] Create `scripts/generate_weekly_email.py`
- [ ] Add Makefile targets
- [ ] Add CLI help text and argument validation

### Testing & Validation
- [ ] Test with empty database
- [ ] Test with single strategy
- [ ] Test with multiple providers per strategy
- [ ] Test with closed positions
- [ ] Validate HTML output in browser
- [ ] Validate email HTML in email client preview
- [ ] Test price fetching fallback (simulate API failures)
- [ ] Verify P/L calculations match portfolio_accounts table

### Documentation
- [ ] Add docstrings to all functions
- [ ] Update `folios-v2/README.md` with HTML generation instructions
- [ ] Add example output screenshots to `docs/`
- [ ] Document data flow and caching strategy

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    folios_v2.db (SQLite)                     │
├─────────────────────────────────────────────────────────────┤
│ strategies, portfolio_accounts, positions, orders,          │
│ strategy_runs, requests, execution_tasks                    │
└────────────────┬────────────────────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────┐
    │   HTMLDataLoader       │  ← Query builder
    │   - load_strategies()  │
    │   - load_positions()   │
    │   - load_orders()      │
    └──────────┬─────────────┘
               │
               ▼
    ┌────────────────────────┐
    │  MarketDataService     │  ← Price enrichment
    │  - get_current_prices()│    (Yahoo Finance → DB fallback)
    └──────────┬─────────────┘
               │
               ▼
    ┌────────────────────────┐
    │  PortfolioEngine       │  ← Value/P&L computation
    │  - compute_cash()      │
    │  - compute_mv()        │
    │  - build_trade_hist()  │
    └──────────┬─────────────┘
               │
               ▼
    ┌────────────────────────┐
    │  HTML Templates        │  ← Rendering
    │  - render_leaderboard()│
    │  - render_strategy()   │
    │  - render_feed()       │
    └──────────┬─────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│      public/ directory                │
├──────────────────────────────────────┤
│ index.html                            │
│ feed.html                             │
│ strategy-{id}.html (many)             │
│ email/week-{date}.html                │
│ email/latest.html                     │
└──────────────────────────────────────┘
```

## Key Design Decisions

### 1. Provider Scoping
- **folios-py**: Uses string `provider` column (e.g., "openai", "gemini", "anthropic")
- **folios-v2**: Uses `ProviderId` enum with same values
- **Strategy**: Query using `provider_id` column, convert to string for display

### 2. Portfolio Value Source
- **Option A**: Recompute from positions + orders (like folios-py)
- **Option B**: Read from `portfolio_accounts` table (cash_balance + equity_value)
- **Recommendation**: Use Option A for consistency, but validate against portfolio_accounts

### 3. Payload Decoding
- All models use `payload: JSON` for extensible storage
- Need to decode JSON and merge with table columns
- Use Pydantic models from `domain/` layer when available

### 4. Price Caching Strategy
- Fetch all symbols upfront (batch by 40)
- Cache in-memory for entire generation run
- Fallback order: Yahoo Finance → quotes table → ohlcv table

### 5. HTML Output Location
- Use `public/` directory at repo root (matches folios-py)
- Add `public/` to `.gitignore` to avoid committing generated files
- Consider adding `.gitkeep` to `public/email/` for directory structure

## Migration Notes

### Schema Differences to Handle

| folios-py | folios-v2 | Handling |
|-----------|-----------|----------|
| `strategy_provider_portfolios` table | `portfolio_accounts` table | Map column names: `portfolio_value_usd` → `cash_balance + equity_value` |
| String provider column | `provider_id` (ProviderId enum) | Convert enum to string for display |
| `performance` JSON column | Part of `payload` JSON | Extract from payload dict |
| Direct column access | Payload + column hybrid | Merge table columns with payload JSON |

### Missing Tables/Features

If folios-py relies on these but they don't exist in folios-v2:
- `quotes` table → May need to add or use alternative price source
- `ohlcv` table → May need to add or rely purely on live API
- `metadata` column on orders → Extract from `payload` JSON

### Recommended Additions

Consider adding to folios-v2 schema:
```python
class QuoteRecord(Base):
    """Live price quotes cache."""
    __tablename__ = "quotes"

    symbol: Mapped[str] = mapped_column(String, primary_key=True)
    price: Mapped[Decimal] = mapped_column(Decimal, nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
```

## Success Criteria

The implementation is complete when:

1. ✅ Running `make generate-html` produces valid HTML files
2. ✅ Leaderboard shows all strategies sorted by performance
3. ✅ Strategy detail pages show positions, cash, P/L breakdown
4. ✅ Activity feed groups orders by date with rationale
5. ✅ Weekly email includes popular holdings, new tickers, strategy summaries
6. ✅ All HTML validates and renders properly in browsers
7. ✅ Portfolio values match between HTML and database
8. ✅ Price fetching handles API failures gracefully
9. ✅ Generation completes in <60s for 100 strategies
10. ✅ Output matches visual style/UX of folios-py

## Future Enhancements

Post-MVP improvements:
- Add charts/visualizations (Chart.js or similar)
- Generate JSON API endpoints alongside HTML
- Add search/filter functionality to leaderboard
- Implement RSS feed for activity
- Add email delivery mechanism (SMTP integration)
- Cache generated HTML with TTL
- Add dark mode CSS
- Generate performance comparison charts
- Add export to CSV/Excel functionality
