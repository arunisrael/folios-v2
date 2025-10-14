# Anthropic Direct Execution Test Results

## Scenario

Validated Anthropic and Gemini provider execution paths using the
`run_single_strategy.py` helper. Anthropic now leverages the direct API executor,
while Gemini still uses the local CLI binary.

- **Strategy ID:** `877be608-8547-4656-9d16-0f395df434dd` (Momentum)
- **Prompt:** "Analyze AAPL and MSFT for investment potential"
- **Anthropic Request:** `79b9930c-3a6f-4f41-ae9b-a3fa8ec37ef2`
- **Gemini Request:** `9d81a050-c698-4ef9-98b4-6b3361e4c045`

```bash
uv run python scripts/run_single_strategy.py \
  877be608-8547-4656-9d16-0f395df434dd \
  --cli gemini,anthropic
```

---

## Anthropic (Direct API) – ✅ Success

**Artifacts:**
- `prompt.txt`
- `response.json`
- `structured.json`
- `parsed.json` (after harvest)

**Highlights:**
- `response.json` captures the raw SDK payload, including `usage`, `total_cost_usd`,
  and `model` metadata.
- `structured.json` contains the `investment_analysis_v1` response parsed from the
  API output (no CLI post-processing required).
- `parsed.json` originates from `UnifiedResultParser` and is ready for portfolio
  execution.

**Key Fields Extracted:**
```json
{
  "provider": "anthropic",
  "model": "claude-sonnet-4-5-20250929",
  "recommendations": [
    {
      "ticker": "MSFT",
      "action": "BUY",
      "allocation_percent": 10.0,
      "confidence": 0.88
    },
    {
      "ticker": "AAPL",
      "action": "HOLD",
      "allocation_percent": 6.0,
      "confidence": 0.75
    }
  ]
}
```

**Exit Code:** `0` (captured in `response.json['exit_code']`)

---

## Gemini (CLI) – ✅ Success

**Artifacts:**
- `prompt.txt`
- `response.json`
- `structured.json` (when a JSON fenced block exists)
- `stderr.txt` (contains CLI warnings such as "Loaded cached credentials.")
- `parsed.json`

**Highlights:**
- CLI output includes model usage for `gemini-2.5-pro` and tool call telemetry.
- `UnifiedResultParser` extracts recommendations from `structured.json` or falls
  back to `response.json['response']`.

**Exit Code:** `0`

---

## Harvest & Lifecycle Verification

```bash
make harvest
```

- Both requests transitioned from `pending` → `succeeded`.
- `parsed.json` regenerated without re-running any provider execution.
- `execution_tasks.metadata['artifact_dir']` now points to the artifact directory.

Database confirmation:

```sql
SELECT id, provider_id, lifecycle_state
FROM requests
WHERE id IN (
  '79b9930c-3a6f-4f41-ae9b-a3fa8ec37ef2',
  '9d81a050-c698-4ef9-98b4-6b3361e4c045'
);
```

Both rows return `succeeded`.

---

## Portfolio Execution Smoke Test

```bash
uv run python scripts/execute_recommendations.py \
  79b9930c-3a6f-4f41-ae9b-a3fa8ec37ef2 \
  877be608-8547-4656-9d16-0f395df434dd \
  --provider-id anthropic \
  --initial-balance 100000 \
  --default-price 450
```

- Created one BUY order for MSFT (allocation 10%).
- Strategy portfolio cash reduced accordingly; equity value increased.
- Validated with:
  ```sql
  SELECT provider_id, cash_balance, equity_value
  FROM portfolio_accounts
  WHERE strategy_id = '877be608-8547-4656-9d16-0f395df434dd';
  ```

---

## Takeaways

- Anthropic direct integration is production-ready; no CLI friction remains.
- Gemini CLI path continues to work and coexist with batches.
- `UnifiedResultParser` handles both artifact layouts consistently.
- Portfolio execution consumes Anthropic recommendations without modification.
