# Folios v2 - Complete Command Reference

## Quick Start

### Execute a Single Strategy (Most Common Use Case)

```bash
# Mixed mode: OpenAI batch + Gemini CLI + Anthropic direct API
uv run python scripts/run_single_strategy.py <STRATEGY_ID> \
  --batch openai \
  --cli gemini,anthropic

# All batch mode (long-running, async results)
uv run python scripts/run_single_strategy.py <STRATEGY_ID> \
  --batch openai,gemini

# Immediate execution only
uv run python scripts/run_single_strategy.py <STRATEGY_ID> \
  --cli openai,gemini,anthropic
```

> Anthropic now executes via the `AnthropicDirectExecutor` (no local CLI required).
> Set `ANTHROPIC_API_KEY` before running.

---

## 1. Strategy Management

### List All Strategies

```bash
make list-strategies
```

**Output format:**
```
<UUID>  <Theme>  <Research Day>
```

### Get Random Strategy

```bash
sqlite3 folios_v2.db "SELECT id, name FROM strategies ORDER BY RANDOM() LIMIT 1"
```

### View Strategy Details

```bash
sqlite3 folios_v2.db "SELECT id, name, status, payload FROM strategies WHERE id = '<STRATEGY_ID>'"
```

---

## 2. Request Submission

### Option A: Single Strategy (Recommended)

Use `scripts/run_single_strategy.py` for maximum flexibility:

```bash
# Template
uv run python scripts/run_single_strategy.py <STRATEGY_ID> \
  [--batch <provider1,provider2>] \
  [--cli <provider1,provider2>]

# Examples
uv run python scripts/run_single_strategy.py 1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --batch openai \
  --cli gemini,anthropic

uv run python scripts/run_single_strategy.py 1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --cli anthropic
```

**When to use:**
- Testing specific strategies
- Mixed batch/CLI execution
- Need immediate results (CLI mode)
- Exercising the direct Anthropic API path without waiting for batch jobs

### Option B: Batch Submit All Strategies

Use `make submit-batch` to submit **all active strategies** via batch API:

```bash
# All providers (OpenAI + Gemini)
make submit-batch

# Specific providers only
make submit-batch PROVIDERS=openai
make submit-batch PROVIDERS=gemini
make submit-batch PROVIDERS=openai,gemini
```

**When to use:**
- Weekly production runs
- Processing all strategies at once
- Only batch mode needed

### Option C: Batch Submit Specific Strategy

```bash
make submit-strategy STRATEGY_ID=<UUID>

# With specific providers
make submit-strategy STRATEGY_ID=<UUID> PROVIDERS=openai
```

**When to use:**
- Single strategy in batch mode only
- Don't need CLI mode

---

## 3. Status Checking

### View All Pending Requests

```bash
make status
```

**Output:**
```
Pending Requests: 8
  - <request-id-1>: openai (batch)
  - <request-id-2>: gemini (cli)
  - ...
```

### Detailed Request Status

```bash
sqlite3 folios_v2.db "
SELECT
  id,
  strategy_id,
  provider_id,
  mode,
  lifecycle_state,
  created_at
FROM requests
WHERE lifecycle_state = 'pending'
ORDER BY created_at DESC
"
```

### Check Specific Strategy Requests

```bash
sqlite3 folios_v2.db "
SELECT
  r.id,
  r.provider_id,
  r.mode,
  r.lifecycle_state,
  r.created_at,
  s.name as strategy_name
FROM requests r
JOIN strategies s ON r.strategy_id = s.id
WHERE r.strategy_id = '<STRATEGY_ID>'
ORDER BY r.created_at DESC
"
```

---

## 4. Harvest Results

### Harvest Pending Requests

```bash
make harvest
```

**What it does:**
- For **batch requests**: Poll provider APIs, download artifacts, parse results
- For **CLI/direct requests**: Parse existing artifacts only (no re-execution)
- Marks `execution_tasks` + `requests` as `succeeded`
- Writes/refreshes `parsed.json` and records provider job IDs when available

**Timing:**
- CLI/direct requests: Harvest immediately after execution completes
- Batch requests: Wait ~24 hours for providers to finish processing

### Harvest with Custom Limit

```bash
uv run python scripts/harvest.py run --limit 50
```

Default limit: 25 requests

---

## 5. Review Results

### Gemini Batch Helpers

Gemini batches take 24+ hours to finish. Use the purpose-built helpers to avoid
blocking regular harvest cycles:

```bash
# Submit a single pending Gemini batch request
uv run python scripts/test_gemini_submit.py

# Inspect local vs remote job status
uv run python scripts/check_gemini_batch.py status

# Download completed Gemini batches
uv run python scripts/harvest_gemini_batches.py
```

Run the status + harvest commands daily via cron for production-like automation.

### View Parsed Recommendations

```bash
# All recommendations for a request
cat artifacts/<REQUEST_ID>/*/parsed.json | jq '.'

# Just the recommendations array
cat artifacts/<REQUEST_ID>/*/parsed.json | jq '.recommendations'

# Specific fields
cat artifacts/<REQUEST_ID>/*/parsed.json | jq '.recommendations[] | {ticker, action, allocation_percent}'
```

### Find All Recommendations for a Strategy

```bash
# Get all request IDs for a strategy
REQUEST_IDS=$(sqlite3 folios_v2.db "
  SELECT id FROM requests
  WHERE strategy_id = '<STRATEGY_ID>'
  AND lifecycle_state = 'succeeded'
")

# View all recommendations
for rid in $REQUEST_IDS; do
  echo "=== Request: $rid ==="
  cat artifacts/$rid/*/parsed.json | jq '.recommendations'
done
```

### Compare Recommendations Across Providers

```bash
# List all succeeded requests for a strategy
sqlite3 folios_v2.db "
SELECT
  provider_id,
  id as request_id
FROM requests
WHERE strategy_id = '<STRATEGY_ID>'
AND lifecycle_state = 'succeeded'
"

# Then manually check each artifact
```

---

## 6. Execute Trades

### Execute Recommendations from a Request

```bash
uv run python scripts/execute_recommendations.py \
  <REQUEST_ID> \
  <STRATEGY_ID> \
  --provider-id <PROVIDER> \
  --initial-balance 100000.0 \
  --live-prices
```

**Parameters:**
- `REQUEST_ID`: The request UUID (from `make status` or database)
- `STRATEGY_ID`: The strategy UUID
- `--provider-id`: Provider name (openai, gemini, anthropic)
- `--initial-balance`: Starting cash (default: $100,000)
- `--live-prices` / `--no-live-prices`: Use real-time Yahoo Finance prices vs simulation

**Example:**
```bash
uv run python scripts/execute_recommendations.py \
  ba042081-af1b-4e84-8ef0-70d4c9b0ec55 \
  1dff269f-412a-4c74-bca1-e9d3ab213d6e \
  --provider-id openai \
  --initial-balance 100000.0 \
  --live-prices
```

**What it does:**
1. Loads `parsed.json` or `structured.json` from artifacts
2. Creates/fetches `PortfolioAccount` for (strategy, provider)
3. For each BUY recommendation:
   - Fetches current price (if `--live-prices`)
   - Calculates position size from allocation_percent
   - Creates `Order` (status=FILLED)
   - Creates `Position` with entry price
   - Updates portfolio cash and equity
4. Saves to database

**Database tables updated:**
- `portfolio_accounts` (upsert)
- `orders` (insert)
- `positions` (insert)

### Execute All Recommendations for a Strategy

```bash
# Get all succeeded requests
REQUESTS=$(sqlite3 folios_v2.db "
  SELECT id, provider_id FROM requests
  WHERE strategy_id = '<STRATEGY_ID>'
  AND lifecycle_state = 'succeeded'
")

# Execute each
# (Manual: run execute_recommendations.py for each request)
```

---

## 7. Portfolio Management

### View Portfolio Accounts

```bash
# All portfolios
sqlite3 folios_v2.db "
SELECT
  strategy_id,
  provider_id,
  cash_balance,
  equity_value,
  (cash_balance + equity_value) as total_value,
  updated_at
FROM portfolio_accounts
ORDER BY strategy_id, provider_id
"

# For specific strategy
sqlite3 folios_v2.db "
SELECT
  provider_id,
  cash_balance,
  equity_value,
  (cash_balance + equity_value) as total_value
FROM portfolio_accounts
WHERE strategy_id = '<STRATEGY_ID>'
"
```

### View Positions

```bash
# All positions for a strategy
sqlite3 folios_v2.db "
SELECT
  provider_id,
  symbol,
  side,
  quantity,
  average_price,
  (quantity * average_price) as position_value,
  opened_at
FROM positions
WHERE strategy_id = '<STRATEGY_ID>'
ORDER BY provider_id, symbol
"

# Open positions only
sqlite3 folios_v2.db "
SELECT * FROM positions
WHERE strategy_id = '<STRATEGY_ID>'
AND closed_at IS NULL
"
```

### View Orders

```bash
# All orders for a strategy
sqlite3 folios_v2.db "
SELECT
  provider_id,
  symbol,
  action,
  quantity,
  limit_price,
  status,
  placed_at,
  filled_at
FROM orders
WHERE strategy_id = '<STRATEGY_ID>'
ORDER BY placed_at DESC
"

# Orders for specific provider
sqlite3 folios_v2.db "
SELECT * FROM orders
WHERE strategy_id = '<STRATEGY_ID>'
AND provider_id = '<PROVIDER>'
"
```

---

## 8. Complete Workflows

### Workflow 1: Full Production Cycle (All Strategies, All Providers)

```bash
# 1. Submit all strategies
make submit-batch PROVIDERS=openai,gemini

# 2. Wait ~24 hours

# 3. Harvest results
make harvest

# 4. Execute trades (manual for each request)
# Use queries from section 6 to get request IDs
```

### Workflow 2: Quick Test (Single Strategy, CLI Only)

```bash
# 1. Pick a random strategy
STRATEGY_ID=$(sqlite3 folios_v2.db "SELECT id FROM strategies ORDER BY RANDOM() LIMIT 1")

# 2. Execute with CLI (immediate results)
uv run python scripts/run_single_strategy.py $STRATEGY_ID \
  --cli gemini,anthropic

# 3. Check status
make status

# 4. Harvest (should complete immediately)
make harvest

# 5. Get request IDs
sqlite3 folios_v2.db "
  SELECT id, provider_id FROM requests
  WHERE strategy_id = '$STRATEGY_ID'
  AND lifecycle_state = 'succeeded'
"

# 6. Execute trades for each request
uv run python scripts/execute_recommendations.py \
  <REQUEST_ID> $STRATEGY_ID \
  --provider-id gemini \
  --no-live-prices

# 7. View portfolio
sqlite3 folios_v2.db "
  SELECT * FROM portfolio_accounts WHERE strategy_id = '$STRATEGY_ID'
"
```

### Workflow 3: Mixed Batch + CLI (Single Strategy)

```bash
# 1. Select strategy
STRATEGY_ID="1dff269f-412a-4c74-bca1-e9d3ab213d6e"

# 2. Submit (OpenAI batch + Gemini/Anthropic CLI)
uv run python scripts/run_single_strategy.py $STRATEGY_ID \
  --batch openai \
  --cli gemini,anthropic

# 3. Harvest CLI results immediately
make harvest

# 4. Execute Gemini + Anthropic trades
# (Get request IDs from status or database)
uv run python scripts/execute_recommendations.py <GEMINI_REQUEST_ID> $STRATEGY_ID --provider-id gemini
uv run python scripts/execute_recommendations.py <ANTHROPIC_REQUEST_ID> $STRATEGY_ID --provider-id anthropic

# 5. Wait ~24 hours for OpenAI batch

# 6. Harvest OpenAI results
make harvest

# 7. Execute OpenAI trades
uv run python scripts/execute_recommendations.py <OPENAI_REQUEST_ID> $STRATEGY_ID --provider-id openai

# 8. Compare portfolios
sqlite3 folios_v2.db "
  SELECT
    provider_id,
    cash_balance,
    equity_value,
    (cash_balance + equity_value) as total
  FROM portfolio_accounts
  WHERE strategy_id = '$STRATEGY_ID'
"
```

---

## 9. Debugging & Troubleshooting

### Check Artifact Directory Contents

```bash
ls -la artifacts/<REQUEST_ID>/*/
```

**Expected files:**
- **Batch mode:** `<provider>_payload.jsonl`, `<provider>_batch_results.jsonl`, `parsed.json`
- **CLI mode:** `prompt.txt`, `response.json`, `parsed.json`, `structured.json`

### View Raw Response

```bash
# Batch
cat artifacts/<REQUEST_ID>/*/<provider>_batch_results.jsonl | jq '.'

# CLI
cat artifacts/<REQUEST_ID>/*/response.json | jq '.'
```

### Check for Failed Requests

```bash
sqlite3 folios_v2.db "
SELECT
  id,
  strategy_id,
  provider_id,
  lifecycle_state
FROM requests
WHERE lifecycle_state IN ('failed', 'timed_out', 'cancelled')
"
```

### Verify Database Entries

```bash
# Count requests by state
sqlite3 folios_v2.db "
SELECT lifecycle_state, COUNT(*) as count
FROM requests
GROUP BY lifecycle_state
"

# Count portfolios
sqlite3 folios_v2.db "SELECT COUNT(*) FROM portfolio_accounts"

# Count positions
sqlite3 folios_v2.db "SELECT COUNT(*) FROM positions WHERE closed_at IS NULL"
```

---

## 10. Available Make Commands

```bash
make help                    # Show all commands
make list-strategies         # List active strategies
make submit-batch            # Submit batch for all strategies
make submit-strategy         # Submit batch for one strategy
make harvest                 # Harvest completed requests
make execute                 # Execute recommendations (deprecated - use script)
make status                  # Show request status
make submit-stale            # Submit stale strategies (>48h)
make workflow                # Full workflow: submit → harvest → execute
make workflow-quick          # Quick test with OpenAI only
make test-cli                # Test CLI executors with 5 strategies
```

---

## 11. Provider-Specific Notes

### OpenAI

- **Batch API**: Requires `OPENAI_API_KEY` in `.env`
- **Processing time**: minutes to a few hours
- **CLI**: Optional `CodexCliExecutor` fallback (disabled by default)
- **Model**: Defaults to `gpt-4o-mini` (override with `OPENAI_BATCH_MODEL`)

### Gemini

- **Batch API**: Requires `GEMINI_API_KEY`
- **Processing time**: 24+ hours (submit → wait → harvest)
- **CLI**: Uses local `gemini` binary with `--output-format json`
- **Model**: Defaults to `gemini-2.5-pro` (override via script flags or env)

### Anthropic

- **Execution mode**: Direct API via `AnthropicDirectExecutor`
- **Batch API**: Not yet supported
- **Environment**: Requires `ANTHROPIC_API_KEY`
- **Model**: Defaults to `claude-sonnet-4-5-20250929` (see `AnthropicDirectExecutor`)

---

## 12. Environment Variables

Recommended minimal `.env`:

```bash
# Provider credentials
OPENAI_API_KEY=sk-...
GEMINI_API_KEY=...
ANTHROPIC_API_KEY=...

# Screener integrations (optional)
FINNHUB_API_KEY=...
FMP_API_KEY=...

# Runtime toggles
FOLIOS_LOCAL_BATCH_FALLBACK=1
OPENAI_BATCH_MODEL=gpt-4o-mini
OPENAI_COMPLETION_WINDOW=24h
GEMINI_BATCH_MODEL=gemini-2.5-pro

# Storage overrides
FOLIOS_DATABASE_URL=sqlite+aiosqlite:///~/Library/Application Support/folios_v2/folios_v2.db
FOLIOS_ARTIFACTS_ROOT=~/Library/Application Support/folios_v2/artifacts
```

Every setting is defined in `src/folios_v2/config.py` if you need to trace defaults.

---

## 13. File Locations

```
folios-v2/
├── folios_v2.db                    # Main database
├── artifacts/                      # Execution results
│   └── <request-id>/
│       └── <task-id>/
│           ├── parsed.json         # Parsed recommendations
│           ├── structured.json     # Structured data
│           └── ...                 # Provider-specific files
├── scripts/
│   ├── run_single_strategy.py     # ⭐ Main execution script
│   ├── submit_batch_requests.py   # Batch submission
│   ├── harvest.py                 # Result harvesting
│   ├── execute_recommendations.py # Trade execution
│   └── show_status.py             # Status display
└── docs/
    ├── full_lifecycle_workflow.md # Detailed workflow guide
    └── COMMAND_REFERENCE.md       # This file
```

---

## 14. Common Queries

### Get Request ID from Strategy and Provider

```bash
sqlite3 folios_v2.db "
SELECT id FROM requests
WHERE strategy_id = '<STRATEGY_ID>'
AND provider_id = '<PROVIDER>'
AND lifecycle_state = 'succeeded'
ORDER BY created_at DESC
LIMIT 1
"
```

### Count Recommendations by Provider

```bash
# Requires parsing all parsed.json files
for dir in artifacts/*/*/; do
  if [ -f "$dir/parsed.json" ]; then
    provider=$(jq -r '.provider' "$dir/parsed.json")
    count=$(jq '.recommendations | length' "$dir/parsed.json")
    echo "$provider: $count recommendations"
  fi
done
```

### Calculate Total Portfolio Value

```bash
sqlite3 folios_v2.db "
SELECT
  SUM(cash_balance + equity_value) as total_value
FROM portfolio_accounts
"
```

### Find Most Active Strategy

```bash
sqlite3 folios_v2.db "
SELECT
  s.name,
  COUNT(r.id) as request_count
FROM strategies s
JOIN requests r ON s.id = r.strategy_id
GROUP BY s.id
ORDER BY request_count DESC
LIMIT 10
"
```

---

## Need Help?

1. Check `docs/full_lifecycle_workflow.md` for detailed workflow explanations
2. Run `make help` to see available commands
3. Check artifact directories for execution details
4. Query database tables for state inspection
