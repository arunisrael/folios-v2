# Anthropic Direct Execution Troubleshooting

> This document replaces the legacy CLI troubleshooting guide. Anthropic requests
> now execute through the official SDK (no local Claude binary).

## Common Failure Modes

### 1. `ExecutionError: ANTHROPIC_API_KEY not found in environment`
- **Symptom:** Request fails immediately; `response.json` contains `{ "error": "ANTHROPIC_API_KEY not found in environment" }`.
- **Fix:** Add the key to `.env` or export it temporarily:
  ```bash
  echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env
  # or
  export ANTHROPIC_API_KEY=sk-ant-...
  ```
  Rerun `uv run python scripts/run_single_strategy.py ... --cli anthropic`.

### 2. `ExecutionError: anthropic package not installed`
- **Symptom:** The executor catches `ImportError` when importing the SDK.
- **Fix:** Install dependencies (`uv pip install -e .[dev]` already pulls in
  `anthropic`). For minimal installs run `uv pip install anthropic`.

### 3. `ParseError: No parseable output found`
- **Symptom:** `make harvest` fails because neither `structured.json` nor
  `response.json` contains structured data.
- **What to check:**
  1. Inspect `artifacts/<request>/<task>/response.json` – look for `structured`
     or error fields.
  2. If the response only contains free-form text, ensure the model prompt still
     instructs Anthropic to emit JSON (`investment_analysis_v1`).
  3. If the API returned Markdown with a JSON block, confirm the block starts
     with ```json for `_extract_structured_json` to work.

### 4. `total_cost_usd` or usage missing
- **Symptom:** Telemetry fields are absent in `response.json`.
- **Fix:** Upgrade the SDK – the bundled version exposes `message.usage`. Run
  `uv pip install --upgrade anthropic` and rerun the request.

### 5. Network / quota failures
- **Symptom:** `response.json` contains `"error": "RateLimitError"` or similar.
- **Fixes:**
  - Confirm account has sufficient credits.
  - Reduce concurrency (Anthropic throttle is already `max_concurrent=1`).
  - Wait and retry via `run_single_strategy.py`.

## Diagnostic Commands

```bash
# Re-run a specific request (creates new request/task)
uv run python scripts/run_single_strategy.py <STRATEGY_ID> --cli anthropic

# Inspect artifacts
ls -la artifacts/<REQUEST_ID>/*/
cat artifacts/<REQUEST_ID>/*/response.json | jq '.'

# Re-parse without rerunning execution
uv run python scripts/harvest.py run --limit 1
```

## Logging Add-ons

Set `ANTHROPIC_LOG_LEVEL=debug` before running to enable verbose SDK logging.
Outputs go to `stderr` and are captured in `response.json['stderr']` via the
executor’s metadata.

## When to Escalate

- Consistent `RateLimitError` despite low volume – contact Anthropic support.
- Schema drift (JSON keys renamed or removed) – update
  `AnthropicDirectExecutor._extract_structured_json` and notify the team.
- Persistent HTTP 5xx – retry with exponential backoff; if reproducible, gather
  timestamps and request IDs for a support ticket.

With the direct integration, most issues boil down to missing credentials or SDK
version mismatches, not CLI authentication quirks.
