# Folios v2

Strictly typed rebuild of the Folios trading workbench. Folios v2 ships a declarative
provider system, async batch+CLI runtimes, and a weekly research cadence backed by a
SQLite persistence layer. The implementation follows the redesign proposals in
`../folios-py/docs/redesign/` but now uses real OpenAI, Gemini, and Anthropic
integrations with optional local fallbacks.

## Tooling
- Python >= 3.11
- `uv` / `pip` for dependency management
- `ruff`, `black`, `mypy --strict`, and `pytest`

### Quickstart
```bash
# Install dependencies (dev extras recommended during development)
uv pip install -e .[dev]

# Run the standard quality suite
make check

# Common operations
make submit-batch           # Submit batch requests for all active strategies
make harvest                # Harvest completed OpenAI batch requests
make execute                # Execute trade recommendations
make status                 # Show request status

# Single-strategy orchestration
uv run python scripts/run_single_strategy.py <STRATEGY_ID> \
  --batch openai --cli gemini,anthropic

# Gemini batch operations (24+ hour processing time)
make gemini-submit          # Submit one Gemini batch request
make gemini-status          # Check Gemini batch job status
make gemini-harvest         # Harvest completed Gemini batches

# Other helpers
make lint-fix               # Ruff autofix
make coverage               # pytest coverage report
make submit-stale           # Queue research for idle strategies
make check-batch-status     # Show all batch job statuses
make help                   # Show all available commands
```

## Provider Credentials

All integrations are configured via environment variables. Defaults live in
`src/folios_v2/config.py`; override them in `.env` before running commands.

| Variable | Purpose | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | Live `/v1/batches` submissions | Optional when local fallback enabled |
| `GEMINI_API_KEY` | Gemini batch jobs | Required for 24h batch pipeline |
| `ANTHROPIC_API_KEY` | Direct Anthropic API executor | Consumed by `AnthropicDirectExecutor` |
| `FINNHUB_API_KEY` | Enables Finnhub screeners | Optional |
| `FMP_API_KEY` | Enables FMP screeners | Optional |
| `FOLIOS_DATABASE_URL` | SQLite connection string | Defaults to `sqlite+aiosqlite:///folios_v2.db` |

When an API key is missing and `FOLIOS_LOCAL_BATCH_FALLBACK` remains enabled, the
provider gracefully falls back to the JSON simulator for offline development.

## Project Layout

```
folios-v2/
├── artifacts/                  # Provider artifacts grouped by request/task id
├── docs/                       # Runbooks, architecture notes, integration reports
├── scripts/                    # Operational helpers (submit, harvest, execute, html)
├── src/folios_v2/              # Application source (domain, providers, runtime, orchestration, cli)
├── tests/                      # Pytest suites
├── public/                     # Generated HTML + email outputs
├── data/                       # Supporting JSON fixtures (e.g., screener mappings)
└── tmp_for_deletion/           # Legacy placeholders slated for removal
```

Implementation status, requirements, and migration notes live in the docs listed below.

## Key Documentation

- `docs/COMMAND_REFERENCE.md` – end-to-end command cheatsheet for day-to-day ops.
- `docs/full_lifecycle_workflow.md` – submission → harvest → portfolio walkthrough.
- `docs/portfolio_execution.md` – explains how recommendations become orders.
- `docs/GEMINI_BATCH_FIX_SUMMARY.md` – current Gemini batch pipeline status.
- `docs/screener_configurations.md` – strategy → screener mapping details.

New contributors should also review `docs/AGENT_ONBOARDING.md` (created alongside this
README update) for a condensed orientation.

## Batch Provider Configuration

Real batch execution now prefers the live OpenAI API when credentials are supplied. Configure the behaviour
with the following environment variables (typically via `.env.local` in development or your secret store in
deployed environments):

| Variable | Description | Default |
| --- | --- | --- |
| `OPENAI_API_KEY` | Credential used for the `/v1/batches` API. Required for real submissions. | _unset_ |
| `OPENAI_API_BASE` | Override the API base URL (for proxies or sandboxes). | `https://api.openai.com` |
| `OPENAI_BATCH_MODEL` | Model used for batch chat completions. | `gpt-4o-mini` |
| `OPENAI_COMPLETION_WINDOW` | OpenAI completion window passed when creating batches. | `24h` |
| `OPENAI_BATCH_SYSTEM_MESSAGE` | System prompt injected ahead of the request prompt. | JSON-only guardrail text |
| `FOLIOS_LOCAL_BATCH_FALLBACK` | Set to `0`/`false` to disable local JSON echo fallback when keys are missing. | `1` |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Credential used for Gemini Batch Mode. Required for real submissions. | _unset_ |
| `GEMINI_BATCH_MODEL` | Gemini model name for batch calls. | `gemini-2.5-pro` |

When `OPENAI_API_KEY` is present (and fallback remains enabled) the container automatically wires the
OpenAI provider plugin to use the real serializer/executor/parser trio defined in `folios_v2.providers.openai.batch`.
Without credentials the previous local JSON simulator remains available for offline development.

## Gemini Batch Workflow

Gemini batches require a different workflow than OpenAI due to their **24+ hour processing time**:

### 1. Submit Batches
```bash
make gemini-submit    # Submit one pending Gemini request
```

This creates a batch job and stores the job ID immediately (no waiting for completion).

### 2. Check Status (Optional)
```bash
make gemini-status    # Check all running Gemini batch jobs
```

Shows job state (PENDING, RUNNING, SUCCEEDED, etc.) and progress.

### 3. Harvest Results (After 24+ Hours)
```bash
make gemini-harvest   # Download and parse completed batches
```

Run this daily via cron or manually once batches complete. See `docs/GEMINI_BATCH_FIX_SUMMARY.md` for detailed instructions.
