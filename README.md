# Folios v2

Strictly typed rebuild of the Folios trading workbench. The project implements the redesigned architecture outlined in `../folios-py/docs/redesign/` with a focus on declarative provider plugins, unified request lifecycles, and a cron-friendly weekly cadence.

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

## Project Layout (in progress)
```
folios-v2/
├── docs/               # Requirements capture and architecture notes
├── scripts/            # Operational helpers (harvest, submit_stale_strategies)
├── src/folios_v2/      # Application source (domain, providers, runtime, orchestration, cli)
└── tests/              # Pytest suites
```

Implementation proceeds in phases; see `docs/requirements.md` for the captured scope and design targets.

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
