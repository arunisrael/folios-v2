# Plan: Harvest and Process Remaining OpenAI Batch Requests

## Overview
This plan outlines the steps to harvest all remaining pending OpenAI batch requests, process the results, and execute the recommendations to create portfolio positions with complete investment thesis rationales.

## Prerequisites
- Python virtual environment activated: `source .venv/bin/activate`
- Database not locked (no other harvest/execution processes running)
- OpenAI API key configured in environment
- Updated `execute_recommendations.py` script (already supports both `rationale` and `investment_thesis` fields)

## Current State
- **Gemini batches:** 16 harvested and executed ✓
- **OpenAI batches:** 1 harvested and executed ✓
- **Remaining OpenAI batches:** ~11 pending (check with `python scripts/show_status.py`)

## Step-by-Step Plan

### Step 1: Check Current Status
**Goal:** Identify how many OpenAI batch requests are pending

```bash
source .venv/bin/activate
python scripts/show_status.py
```

**Expected output:** List of pending requests showing provider type and count

### Step 2: Harvest All Remaining OpenAI Batches
**Goal:** Download and parse all completed OpenAI batch results

```bash
source .venv/bin/activate
python scripts/harvest.py
```

**What this does:**
- Connects to OpenAI API
- Checks status of all pending batch jobs
- Downloads completed batch results to `artifacts/` directory
- Parses JSONL files and extracts recommendations
- Creates `parsed.json` files with structured data
- Marks tasks as SUCCEEDED in database

**Expected behavior:**
- Should process multiple pending requests
- Each completed batch creates a `parsed.json` file
- Parser extracts recommendations from `response.body.choices[0].message.content`
- Recommendations include `investment_thesis` field

**Troubleshooting:**
- If database is locked: Kill any running Python processes with `lsof folios_v2.db` and `kill <PID>`
- If harvest hangs: Check OpenAI API status and credentials

### Step 3: Verify Parsed Results
**Goal:** Confirm all harvested batches have recommendations extracted

```bash
python -c "
import json
from pathlib import Path

# Find all OpenAI parsed.json files modified in last hour
parsed_files = list(Path('artifacts').glob('*/*/parsed.json'))
recent_openai = [
    f for f in parsed_files
    if f.stat().st_mtime > (Path().stat().st_mtime - 3600)
    and 'openai' in json.loads(f.read_text()).get('provider', '')
]

print(f'Found {len(recent_openai)} recently harvested OpenAI batches\n')

strategies_to_execute = []
for parsed_file in recent_openai:
    with open(parsed_file) as f:
        data = json.load(f)

    request_id = data.get('request_id')
    strategy_id = data.get('strategy_id')
    rec_count = len(data.get('recommendations', []))

    if rec_count > 0:
        strategies_to_execute.append((request_id, strategy_id, rec_count))
        print(f'Request: {request_id}')
        print(f'Strategy: {strategy_id}')
        print(f'Recommendations: {rec_count}')
        print('---')

print(f'\nTotal strategies ready for execution: {len(strategies_to_execute)}')

# Save for next step
import pickle
with open('/tmp/openai_strategies_to_execute.pkl', 'wb') as f:
    pickle.dump(strategies_to_execute, f)
"
```

**Expected output:** List of request IDs, strategy IDs, and recommendation counts

### Step 4: Get Strategy Names from Database
**Goal:** Enrich the execution list with strategy names for better tracking

```bash
python -c "
import sqlite3
import pickle
from pathlib import Path

# Load strategies from previous step
with open('/tmp/openai_strategies_to_execute.pkl', 'rb') as f:
    strategies = pickle.load(f)

# Get strategy names from database
conn = sqlite3.connect('folios_v2.db')
cursor = conn.cursor()

enriched_strategies = []
for request_id, strategy_id, rec_count in strategies:
    cursor.execute('SELECT name FROM strategies WHERE id = ?', (strategy_id,))
    row = cursor.fetchone()
    strategy_name = row[0] if row else 'Unknown Strategy'
    enriched_strategies.append((request_id, strategy_id, strategy_name, rec_count))
    print(f'{strategy_name}: {rec_count} recommendations')
    print(f'  Request: {request_id}')
    print(f'  Strategy: {strategy_id}')
    print()

conn.close()

# Save enriched list
with open('/tmp/openai_strategies_enriched.pkl', 'wb') as f:
    pickle.dump(enriched_strategies, f)

print(f'Total: {len(enriched_strategies)} strategies')
"
```

### Step 5: Execute All OpenAI Recommendations
**Goal:** Create orders and positions with investment thesis rationales

```bash
python -c "
import subprocess
import time
import pickle
from pathlib import Path

# Load enriched strategies
with open('/tmp/openai_strategies_enriched.pkl', 'rb') as f:
    strategies = pickle.load(f)

print(f'Executing {len(strategies)} OpenAI strategies\n')

results = []
for i, (request_id, strategy_id, strategy_name, rec_count) in enumerate(strategies, 1):
    print(f'[{i}/{len(strategies)}] {strategy_name[:40]}... ', end='', flush=True)

    cmd = [
        'python', 'scripts/execute_recommendations.py',
        request_id,
        strategy_id,
        '--provider-id', 'openai',
        '--initial-balance', '100000'
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=Path.cwd()
        )

        if result.returncode == 0:
            print('✓')
            results.append((strategy_name, 'SUCCESS', rec_count))
        else:
            print('✗')
            results.append((strategy_name, 'FAILED', rec_count))
            print(f'  Error: {result.stderr[:200]}')
    except subprocess.TimeoutExpired:
        print('✗ TIMEOUT')
        results.append((strategy_name, 'TIMEOUT', rec_count))
    except Exception as e:
        print(f'✗ ERROR: {e}')
        results.append((strategy_name, 'ERROR', rec_count))

    # Small delay to avoid database contention
    time.sleep(0.5)

# Summary
print(f'\n{'='*70}')
print('EXECUTION SUMMARY')
print(f'{'='*70}')
success_count = sum(1 for _, status, _ in results if status == 'SUCCESS')
total_recs = sum(rec_count for _, status, rec_count in results if status == 'SUCCESS')
print(f'Strategies Executed: {success_count}/{len(results)}')
print(f'Total Recommendations: {total_recs}')
print(f'\nDetails:')
for name, status, rec_count in results:
    icon = '✓' if status == 'SUCCESS' else '✗'
    print(f'{icon} {name}: {rec_count} recs - {status}')
print(f'{'='*70}')
"
```

**What this does:**
- Executes each strategy's recommendations sequentially
- Fetches live prices from Yahoo Finance for each ticker
- Creates portfolio accounts (if not exists) with $100,000 initial balance
- Creates orders with investment thesis in metadata
- Creates positions for each order
- Updates portfolio cash and equity values
- Adds 0.5 second delay between executions to prevent database locking

**Expected results:**
- All strategies should execute successfully
- Each order should have investment thesis saved in `order.metadata.rationale`
- Portfolio totals should equal $100,000 (cash + equity)

### Step 6: Verify All Orders Have Investment Thesis
**Goal:** Confirm all OpenAI orders were saved with complete rationales

```bash
python -c "
import sqlite3
import json
from pathlib import Path

db_path = Path('folios_v2.db')
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Check OpenAI orders with rationales
cursor.execute('''
    SELECT o.symbol, o.payload, s.name
    FROM orders o
    JOIN strategies s ON o.strategy_id = s.id
    WHERE o.provider_id = 'openai'
    ORDER BY s.name, o.symbol
    LIMIT 10
''')

orders = cursor.fetchall()
print('Sample OpenAI Orders with Investment Thesis:\n')

for symbol, payload_str, strategy_name in orders:
    payload = json.loads(payload_str)
    metadata = payload.get('metadata', {})
    rationale = metadata.get('rationale', '')

    print(f'{strategy_name}: {symbol}')
    if rationale:
        print(f'  ✓ Thesis: {rationale[:100]}...')
    else:
        print(f'  ⚠️  No rationale found')
    print()

# Get summary statistics
cursor.execute('SELECT COUNT(*) FROM orders WHERE provider_id = \"openai\"')
total_orders = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM positions WHERE provider_id = \"openai\"')
total_positions = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM portfolio_accounts WHERE provider_id = \"openai\"')
total_portfolios = cursor.fetchone()[0]

cursor.execute('''
    SELECT COUNT(*) FROM orders
    WHERE provider_id = 'openai'
    AND json_extract(payload, '$.metadata.rationale') IS NOT NULL
    AND json_extract(payload, '$.metadata.rationale') != ''
''')
orders_with_rationale = cursor.fetchone()[0]

print('='*70)
print('FINAL OPENAI SUMMARY:')
print(f'  Portfolio Accounts: {total_portfolios}')
print(f'  Total Orders: {total_orders}')
print(f'  Orders with Investment Thesis: {orders_with_rationale}/{total_orders}')
print(f'  Total Positions: {total_positions}')
print(f'  Success Rate: {orders_with_rationale/total_orders*100:.1f}%' if total_orders > 0 else '  Success Rate: N/A')
print('='*70)

conn.close()
"
```

**Expected output:**
- All OpenAI orders should have investment thesis
- Success rate should be 100%
- Portfolio accounts, orders, and positions counts should match

### Step 7: Combined Summary (All Providers)
**Goal:** Get overview of all harvested and executed strategies

```bash
python -c "
import sqlite3
from pathlib import Path

conn = sqlite3.connect('folios_v2.db')
cursor = conn.cursor()

print('COMPLETE HARVEST & EXECUTION SUMMARY')
print('='*70)

for provider in ['gemini', 'openai', 'anthropic']:
    cursor.execute('SELECT COUNT(*) FROM portfolio_accounts WHERE provider_id = ?', (provider,))
    portfolios = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM orders WHERE provider_id = ?', (provider,))
    orders = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM positions WHERE provider_id = ?', (provider,))
    positions = cursor.fetchone()[0]

    cursor.execute('''
        SELECT COUNT(*) FROM orders
        WHERE provider_id = ?
        AND json_extract(payload, '\$.metadata.rationale') IS NOT NULL
        AND json_extract(payload, '\$.metadata.rationale') != ''
    ''', (provider,))
    with_rationale = cursor.fetchone()[0]

    print(f'\n{provider.upper()}:')
    print(f'  Portfolios: {portfolios}')
    print(f'  Orders: {orders}')
    print(f'  Positions: {positions}')
    print(f'  With Rationale: {with_rationale}/{orders}')

# Grand totals
cursor.execute('SELECT COUNT(*) FROM portfolio_accounts')
total_portfolios = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM orders')
total_orders = cursor.fetchone()[0]

cursor.execute('SELECT COUNT(*) FROM positions')
total_positions = cursor.fetchone()[0]

cursor.execute('''
    SELECT COUNT(*) FROM orders
    WHERE json_extract(payload, '\$.metadata.rationale') IS NOT NULL
    AND json_extract(payload, '\$.metadata.rationale') != ''
''')
total_with_rationale = cursor.fetchone()[0]

print(f'\n{'='*70}')
print('GRAND TOTALS:')
print(f'  Portfolio Accounts: {total_portfolios}')
print(f'  Total Orders: {total_orders}')
print(f'  Total Positions: {total_positions}')
print(f'  Orders with Rationale: {total_with_rationale}/{total_orders}')
print(f'  Coverage: {total_with_rationale/total_orders*100:.1f}%' if total_orders > 0 else '  Coverage: N/A')
print('='*70)

conn.close()
"
```

## Important Notes

### Troubleshooting Tips

1. **Database Locked Error:**
   ```bash
   lsof folios_v2.db
   kill <PID>
   ```

2. **Parser Not Finding Recommendations:**
   - Check `parsed.json` structure
   - Verify unified_parser.py is using correct path for OpenAI responses
   - OpenAI structure: `response.body.choices[0].message.content` (JSON string)

3. **Missing Investment Thesis:**
   - Ensure `execute_recommendations.py` line 229 has:
     ```python
     rationale = rec.get("rationale") or rec.get("investment_thesis", "")
     ```

4. **Failed Executions:**
   - Check if ticker is valid and tradeable
   - Verify Yahoo Finance is accessible
   - Ensure portfolio account doesn't already exist with different provider

### Field Name Mapping

Different providers use different field names:

| Provider | Rationale Field | Allocation Field |
|----------|----------------|------------------|
| Gemini | `investment_thesis` | `position_size_pct` |
| OpenAI | `investment_thesis` | `position_size_pct` |
| Anthropic | `rationale` | `allocation_percent` |

The updated `execute_recommendations.py` script handles both naming conventions automatically.

## Success Criteria

✓ All pending OpenAI batch requests harvested
✓ All `parsed.json` files contain recommendations
✓ All recommendations executed without errors
✓ All orders have investment thesis in metadata
✓ Portfolio balances correct (cash + equity = $100,000)
✓ Database shows 100% coverage for investment thesis

## Next Steps After Completion

1. Review portfolio allocations across all strategies
2. Generate HTML reports for strategy performance
3. Consider submitting new batch requests for stale strategies
4. Monitor positions and update with market data
5. Implement portfolio rebalancing logic if needed

## Commands Reference

Quick command reference for common operations:

```bash
# Check status
python scripts/show_status.py

# Harvest batches
python scripts/harvest.py

# Execute single strategy
python scripts/execute_recommendations.py <REQUEST_ID> <STRATEGY_ID> --provider-id openai

# Check portfolios
python scripts/check_portfolios.py

# Generate HTML
python scripts/generate_public_html.py
```
