# Agent Onboarding Guide

Welcome to Folios v2. This cheat sheet condenses the moving pieces you need to
reason about before touching the codebase.

## Core Concepts

- **Strategies** and their schedules live in SQLite (`folios_v2.db`) and are
  managed via repositories under `src/folios_v2/persistence/sqlite/`.
- **Requests** represent provider executions (batch or CLI/direct). Artifacts
  land in `artifacts/<request>/<task>/` and are parsed by
  `UnifiedResultParser`.
- **Providers** are plugged in through `ProviderPlugin` instances that the
  service container wires up. OpenAI + Gemini support batch + CLI, while
  Anthropic executes via a direct API helper but is surfaced as CLI mode for
  compatibility.

## Daily Driver Commands

```bash
uv pip install -e .[dev]   # one-time tooling install
make check                 # lint + mypy + pytest
make status                # pending request snapshot
make harvest               # parse outputs + update lifecycle state
uv run python scripts/run_single_strategy.py <STRATEGY_ID> --batch openai --cli gemini,anthropic
uv run python scripts/execute_recommendations.py <REQUEST_ID> <STRATEGY_ID> --provider-id gemini
```

Gemini batch flows require the helper scripts in `scripts/` (see
`docs/COMMAND_REFERENCE.md#gemini-batch-helpers`).

## Provider Configuration

Set these keys in `.env` before invoking anything that hits the network:

| Provider  | Variable             | Notes |
|-----------|----------------------|-------|
| OpenAI    | `OPENAI_API_KEY`     | Enables `/v1/batches`. Local JSON fallback stays active when the key is absent and `FOLIOS_LOCAL_BATCH_FALLBACK=1`. |
| Gemini    | `GEMINI_API_KEY`     | Needed for real batch jobs (`scripts/test_gemini_submit.py`). |
| Anthropic | `ANTHROPIC_API_KEY`  | Consumed by `AnthropicDirectExecutor` (no CLI binary required). |
| Screeners | `FINNHUB_API_KEY`, `FMP_API_KEY` | Optional but unlock Finnhub/FMP screener providers. |

Additional toggles (artifact root, default models, completion windows) are
defined in `src/folios_v2/config.py`.

## File Map

```
src/folios_v2/
├── container.py           # Composition root (settings → services)
├── orchestration/         # Request/batch/schedule coordination
├── providers/             # Plugin definitions + executors
├── runtime/               # Batch + CLI/direct runtimes
├── screeners/             # Finnhub/FMP integration
├── persistence/           # SQLite models, repositories, unit of work
└── utils/                 # Time + Decimal helpers
scripts/
├── run_single_strategy.py # Primary orchestration entry point
├── harvest.py             # Multi-provider harvest pass
├── harvest_gemini_batches.py, test_gemini_submit.py, check_gemini_batch.py
│                           # Gemini long-running workflow helpers
└── execute_recommendations.py
```

## Frequently Used Docs

- `docs/COMMAND_REFERENCE.md` – full command cheat sheet
- `docs/full_lifecycle_workflow.md` – end-to-end walkthrough (submit → harvest → execute)
- `docs/portfolio_execution.md` – portfolio account + order mechanics
- `docs/screener_configurations.md` – 76 strategy → screener mappings
- `docs/GEMINI_BATCH_FIX_SUMMARY.md` – status of Gemini timeout fixes and tooling

## Open Questions / TODOs

- **Sell-side execution**: `scripts/execute_recommendations.py` only handles BUY
  flows. Tickets to add SELL/rebalance support are tracked inline in the script.
- **Unified monitoring**: Gemini batch runs still rely on ad-hoc scripts; weigh
  the value of moving them into Typer commands under `folios_v2.cli`.
- **Test coverage gaps**: Market data services, unified parser, and the direct
  Anthropic executor need dedicated tests (see `TEST_COVERAGE_ANALYSIS.md`).

## Quick Validation Checklist

After modifying provider flows or runtimes, you should be able to:

1. `make submit-batch` (OpenAI) → confirm requests enter `pending`.
2. `uv run python scripts/run_single_strategy.py <ID> --cli anthropic` → ensure
   artifacts contain `structured.json` from the direct API call.
3. `make harvest` → verify `parsed.json` is regenerated and lifecycle states flip to `succeeded`.
4. `uv run python scripts/execute_recommendations.py ... --no-live-prices` →
   confirm portfolio balances change as expected.

If any step fails, capture the error, note the provider/task IDs, and update the
relevant troubleshooting doc (`docs/ANTHROPIC_TROUBLESHOOTING.md` or
`docs/GEMINI_BATCH_FIX_SUMMARY.md`).

Happy shipping!
