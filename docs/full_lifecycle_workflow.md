# Full Lifecycle Workflow: Strategy Execution to Portfolio Updates

## Overview

This document describes the complete end-to-end workflow for executing a strategy across multiple AI providers, from submission through trade execution and portfolio updates.

## Test Case: David Dreman Strategy

**Strategy ID:** `1dff269f-412a-4c74-bca1-e9d3ab213d6e`
**Strategy Name:** David Dreman Strategy
**Execution Date:** 2025-10-08

**Providers:**
- OpenAI (Batch Mode) – ~24h processing window
- Gemini (CLI Mode) – local CLI binary (≈5–10 min)
- Anthropic (Direct API in CLI mode) – immediate execution via SDK

## Workflow Steps

### 1. Plan & Enqueue Strategies

New batched workflows begin by identifying which strategies need research. Run:

```bash
make plan-strategies
```

This surfaces active strategies lacking recent submissions. To enqueue batch work for all (or specific) providers:

```bash
make enqueue-strategies PROVIDERS=openai,gemini
```

At this point only database rows are created (no provider traffic yet). Each provider/strategy pair receives one `requests` row and one `execution_tasks` row with lifecycle state `pending`.

---

### 2. Submit Batch Jobs

Queue serialization has prepared payloads, but nothing has been sent upstream yet. Execute:

```bash
make submit-batch-jobs PROVIDERS=openai,gemini
```

This command serializes payloads (if absent), hits each provider’s batch API, stores the returned `provider_job_id`, and moves requests/tasks into `running`.

---

### 3. Poll Provider Status

Long-running providers (OpenAI, Gemini) remain in `running` until we observe completion. Poll them periodically:

```bash
make poll-batch-status PROVIDERS=openai,gemini
```

Tasks move to `awaiting_results` once a provider reports `completed`. Failures or cancellations flip the lifecycle to `failed`, capturing poll metadata in `execution_tasks.metadata`.

### 4. Harvest Results

After jobs reach `awaiting_results`, download artifacts and parse them:

```bash
make harvest-batch-results
```

**What happens now:**
- CLI/direct requests are parsed immediately and transition to `succeeded`.
- Batch requests with `awaiting_results` download provider output, store the files under `artifacts/<request>/<task>/`, write `parsed.json`, and mark both task and request as `succeeded`.

**Files created per request:**
```
artifacts/
├── ba042081-af1b-4e84-8ef0-70d4c9b0ec55/  # OpenAI batch
│   └── c11a1110-0156-45d5-9f45-4a2089d8705c/
│       ├── openai_payload.jsonl          # Submitted request
│       ├── openai_batch_results.jsonl    # Downloaded from OpenAI
│       ├── parsed.json                   # Parsed recommendations
│       └── structured.json               # Structured data (if available)
├── 744ca953-219a-4238-9427-c528580d7393/  # Gemini CLI
│   └── 4f0b40fd-9ddb-43de-833d-4c4ba68b72f0/
│       ├── prompt.txt                    # Submitted prompt
│       ├── response.json                 # CLI response
│       ├── parsed.json                   # Parsed recommendations
│       └── structured.json               # Structured data (if available)
└── <anthropic-request-id>/               # Anthropic direct API
    └── <task-id>/
        ├── prompt.txt
        ├── response.json
        ├── parsed.json
        └── structured.json
```

---

### 4. Review Recommendations

Inspect the parsed recommendations from each provider:

```bash
# OpenAI
cat artifacts/ba042081-af1b-4e84-8ef0-70d4c9b0ec55/*/parsed.json | jq '.recommendations'

# Gemini
cat artifacts/744ca953-219a-4238-9427-c528580d7393/*/parsed.json | jq '.recommendations'

# Anthropic
cat artifacts/<anthropic-request-id>/*/parsed.json | jq '.recommendations'
```

**Expected format:**
```json
{
  "recommendations": [
    {
      "ticker": "AAPL",
      "action": "BUY",
      "entry_price": 150.00,
      "target_price": 180.00,
      "stop_loss": 140.00,
      "allocation_percent": 5.0,
      "rationale": "Strong fundamentals..."
    }
  ]
}
```

---

### 5. Execute Trades

Convert recommendations into orders and positions:

```bash
# Execute OpenAI recommendations (single request)
uv run python scripts/execute_recommendations.py \
  ba042081-af1b-4e84-8ef0-70d4c9b0ec55 \
  1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --provider-id openai \
  --initial-balance 100000.0 \
  --live-prices

# Execute Gemini recommendations
uv run python scripts/execute_recommendations.py \
  744ca953-219a-4238-9427-c528580d7393 \
  1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --provider-id gemini \
  --initial-balance 100000.0 \
  --live-prices

# Execute Anthropic recommendations
uv run python scripts/execute_recommendations.py \
  <anthropic-request-id> \
  1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --provider-id anthropic \
  --initial-balance 100000.0 \
  --live-prices
```

**What happens:**
1. Loads `parsed.json` or `structured.json` from artifact directory
2. Creates or fetches `PortfolioAccount` for (strategy_id, provider_id)
3. For each **BUY** recommendation:
   - Fetches current price from Yahoo Finance (if `--live-prices`)
   - Calculates position size based on allocation percent
   - Creates `Order` with status=FILLED
   - Creates `Position` with entry price and quantity
   - Updates portfolio cash and equity balances
4. Saves all changes to database

**Database updates:**
- Rows added to `orders` table
- Rows added to `positions` table
- Row updated/inserted in `portfolio_accounts` table

---

For bulk execution across all completed requests, run:

```bash
make execute-ready PROVIDERS=openai,gemini BALANCE=100000
```

This helper loops through every `succeeded` research request, loads the parsed artifacts, and applies the portfolio execution engine sequentially.

### 6. Verify Portfolios

Check portfolio balances and positions:

```bash
# View portfolio accounts
sqlite3 folios_v2.db "
SELECT
  strategy_id,
  provider_id,
  cash_balance,
  equity_value,
  (cash_balance + equity_value) as total_value,
  updated_at
FROM portfolio_accounts
WHERE strategy_id = '1dff269f-412a-4c74-bca1-e9d3ab213d6e'
"

# View positions
sqlite3 folios_v2.db "
SELECT
  provider_id,
  symbol,
  quantity,
  average_price,
  (quantity * average_price) as position_value,
  opened_at
FROM positions
WHERE strategy_id = '1dff269f-412a-4c74-bca1-e9d3ab213d6e'
ORDER BY provider_id, symbol
"

# View orders
sqlite3 folios_v2.db "
SELECT
  provider_id,
  symbol,
  action,
  quantity,
  limit_price,
  status,
  placed_at
FROM orders
WHERE strategy_id = '1dff269f-412a-4c74-bca1-e9d3ab213d6e'
ORDER BY placed_at DESC
"
```

**Expected results:**
- 3 portfolio accounts (one per provider): openai, gemini, anthropic
- Each starting with $100,000 initial balance
- Cash reduced by total investment amount
- Equity increased by total position value
- Multiple positions based on recommendations
- Multiple orders (all with status=FILLED)

---

## Timeline Summary

| Step | Action | Duration | State |
|------|--------|----------|-------|
| 1 | `make plan-strategies` | < 1 sec | Identifies stale strategies |
| 1 | `make enqueue-strategies` | < 1 sec | Requests/tasks created (`pending`) |
| 2 | `make submit-batch-jobs` | < 5 sec | Provider job IDs stored (`running`) |
| 3 | `make poll-batch-status` | < 1 sec | Jobs transition to `awaiting_results` |
| 4 | `make harvest-batch-results` | Depends on download | Requests → `succeeded` |
| 5 | `make execute-ready` | < 2 min | Orders, positions, portfolios updated |
| 6 | Manual verification | < 1 min | Inspect database tables |

---

## Complete Command Sequence

```bash
# 1. Identify and enqueue strategies
make plan-strategies
make enqueue-strategies PROVIDERS=openai,gemini

# 2. Submit provider jobs
make submit-batch-jobs PROVIDERS=openai,gemini

# 3. Poll status periodically (repeat until completed)
make poll-batch-status PROVIDERS=openai,gemini

# 4. Harvest results when jobs complete
make harvest-batch-results

# 5. Execute portfolios for completed research
make execute-ready PROVIDERS=openai,gemini BALANCE=100000

# 6. Inspect status/portfolios as needed
make status
sqlite3 folios_v2.db "SELECT * FROM portfolio_accounts WHERE strategy_id = '1dff269f-412a-4c74-bca1-e9d3ab213d6e'"
```

---

## Key Files

### Scripts
- `scripts/run_single_strategy.py` - Unified strategy submission (batch + CLI)
- `scripts/harvest.py` - Download and parse results
- `scripts/execute_recommendations.py` - Execute trades
- `scripts/show_status.py` - Show request status

### Database Tables
- `strategies` - Strategy definitions
- `requests` - Research requests (one per provider)
- `execution_tasks` - Tasks for each request
- `portfolio_accounts` - Portfolio balances per (strategy, provider)
- `positions` - Open positions
- `orders` - Trade orders

### Artifact Directories
- `artifacts/<request_id>/<task_id>/` - Results for each execution

---

## Notes

1. **Batch vs CLI timing:**
   - Batch requests submit instantly but process in ~24h
   - CLI requests execute immediately (5-10 min)

2. **Harvest behavior:**
   - For batch: polls provider API, downloads if ready
   - For CLI: results already exist locally, just parses them

3. **Portfolio isolation:**
   - Each (strategy, provider) pair gets its own portfolio account
   - Allows comparing performance across providers

4. **Initial balance:**
   - Configurable via `--initial-balance` flag
   - Default: $100,000

5. **Live vs simulated prices:**
   - `--live-prices`: Fetch real-time prices from Yahoo Finance
   - `--no-live-prices`: Use simulation price ($100.00)
