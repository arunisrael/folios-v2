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

### 1. Strategy Submission

Use the new unified script to submit a strategy across multiple providers:

```bash
uv run python scripts/run_single_strategy.py \
  1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --batch openai \
  --cli gemini,anthropic
```

**What happens:**
- **OpenAI Batch**: Creates request in database, submits to OpenAI Batch API, receives job ID, returns immediately (<1s)
- **Gemini CLI**: Creates request in database, executes the `gemini` CLI binary, writes artifacts (≈5–10 min)
- **Anthropic Direct**: Creates request in database, calls the Anthropic SDK, writes artifacts immediately (≈30–60s)

**Database entries created:**
- 3 rows in `requests` table (one per provider)
- 3 rows in `execution_tasks` table (one per provider)

**Request IDs (from test):**
- OpenAI: `ba042081-af1b-4e84-8ef0-70d4c9b0ec55`
- Gemini: `744ca953-219a-4238-9427-c528580d7393`
- Anthropic: `<anthropic-request-id>` (typically succeeds within the same run)

---

### 2. Check Status

Monitor the status of all pending requests:

```bash
make status
```

**Example output:**
```
Pending Requests: 8
  - ba042081-af1b-4e84-8ef0-70d4c9b0ec55: openai (batch) [PENDING - waiting for OpenAI]
  - 744ca953-219a-4238-9427-c528580d7393: gemini (cli) [PENDING - CLI completed, needs harvest]
  - <anthropic-request-id>: anthropic (cli) [PENDING - CLI completed, needs harvest]
```

**States:**
- **Batch requests**: Remain `pending` until OpenAI completes processing (~24h)
- **CLI/direct requests**: Remain `pending` until harvested (execution already finished)

---

### 3. Harvest Results

Process completed requests and parse their results:

```bash
make harvest
```

**What happens:**
- Scans `requests` table for `pending` requests
- For **batch requests**:
  - Checks if the provider job has completed (polling OpenAI/Gemini APIs)
  - On completion, downloads results into `artifacts/<request>/<task>/`
  - Parses JSONL results into `parsed.json`
  - Updates request to `succeeded`
- For **CLI/direct requests**:
  - Uses existing artifacts (no re-execution)
  - Parses `structured.json` / `response.json`
  - Updates request to `succeeded`

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
# Execute OpenAI recommendations
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
| 1 | Submit OpenAI batch | < 1 sec | Request created, job submitted |
| 1 | Execute Gemini CLI | 5-10 min | Request created, execution completes |
| 1 | Execute Anthropic CLI | 5-10 min | Request created, execution completes |
| 2 | Check status | < 1 sec | Shows all pending requests |
| 3 | Harvest CLI results | < 5 sec | CLI requests → succeeded |
| 3 | Wait for OpenAI batch | ~24 hours | Batch request still pending |
| 3 | Harvest OpenAI results | < 10 sec | Batch request → succeeded |
| 4 | Review recommendations | < 1 min | Manual inspection |
| 5 | Execute trades (all) | < 2 min | Orders + positions created |
| 6 | Verify portfolios | < 1 min | Check database tables |

---

## Complete Command Sequence

```bash
# 1. Submit strategy
uv run python scripts/run_single_strategy.py \
  1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --batch openai \
  --cli gemini,anthropic

# 2. Check status (anytime)
make status

# 3. Harvest CLI results (after 10 min)
make harvest

# 4. Review Gemini recommendations
cat artifacts/*/*/parsed.json | jq '.recommendations'

# 5. Execute Gemini trades
uv run python scripts/execute_recommendations.py \
  <gemini-request-id> \
  1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --provider-id gemini

# 6. Execute Anthropic trades
uv run python scripts/execute_recommendations.py \
  <anthropic-request-id> \
  1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --provider-id anthropic

# 7. Wait ~24 hours for OpenAI batch...

# 8. Harvest OpenAI results (after ~24h)
make harvest

# 9. Execute OpenAI trades
uv run python scripts/execute_recommendations.py \
  ba042081-af1b-4e84-8ef0-70d4c9b0ec55 \
  1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --provider-id openai

# 10. Verify final portfolios
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
