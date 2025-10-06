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

# Additional helpers
make lint-fix       # Ruff autofix
make coverage       # pytest coverage report
make harvest        # Execute pending requests once
make submit-stale   # Queue research for idle strategies
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
