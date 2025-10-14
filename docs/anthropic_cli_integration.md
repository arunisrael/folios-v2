# Anthropic Direct API Integration

Anthropic support in Folios v2 now runs through the official Python SDK instead of
the Claude CLI. This note explains how the provider plugin is wired, what the
executor does, and how artifacts are produced.

## Architecture Overview

- **Provider plugin:** `ANTHROPIC_PLUGIN` in
  `src/folios_v2/providers/anthropic/plugin.py` registers a CLI-capable plugin
  whose executor is `AnthropicDirectExecutor` and parser is `AnthropicResultParser`.
- **Execution mode:** Still reported as `ExecutionMode.CLI` so existing orchestration
  flows (request metadata, harvest logic) require no changes.
- **Throttle:** `ProviderThrottle(max_concurrent=1, requests_per_minute=30)` keeps
  calls serialised.

## AnthropicDirectExecutor

Location: `src/folios_v2/providers/anthropic/direct_executor.py`

Responsibilities:

1. Read the research prompt from `ctx.request.metadata['strategy_prompt']`.
2. Persist `prompt.txt` inside the artifact directory for auditing.
3. Instantiate the SDK client with `ANTHROPIC_API_KEY` (environment variable).
4. Call `client.messages.create` with the configured model (default
   `claude-sonnet-4-5-20250929`) and a single user message containing the prompt.
5. Merge streaming text blocks into a single response string.
6. Attempt to parse structured JSON directly (`json.loads`) or via a fenced
   ```json code block (using `_extract_structured_json`).
7. Write `response.json` with metadata and `structured.json` when parsing succeeds.
8. Return `CliResult` populated with exit code, artifact paths, and metadata.

Error handling: exceptions are caught, recorded inside `response.json['error']`, and
reflected in the returned `CliResult` (`exit_code=1`).

## AnthropicResultParser

`src/folios_v2/providers/anthropic/plugin.py` wires a custom parser that
prioritises:

1. `structured.json` → authoritative structured payload.
2. `response.json` → uses `structured` field if present, otherwise returns the
   entire response for manual inspection.

The parser output feeds directly into `UnifiedResultParser`, so harvest and trade
execution see a consistent shape (`recommendations`, `market_context`, etc.).

## Configuration

| Setting | Source | Default |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Environment | _required_ |
| `CLAUDE_CLI_PATH` | Environment | Ignored (legacy) |
| Model | `AnthropicDirectExecutor.model` | `claude-sonnet-4-5-20250929` |

Set `ANTHROPIC_API_KEY` in `.env` before running any Anthropic flows:

```bash
echo 'ANTHROPIC_API_KEY=sk-ant-...' >> .env
```

## Running a Strategy via Anthropic

```bash
uv run python scripts/run_single_strategy.py \
  <STRATEGY_ID> \
  --cli anthropic
```

- The script creates a request/task pair, queues metadata, and immediately calls
  the executor.
- Artifacts appear under `artifacts/<request>/<task>/`.
- Run `make harvest` (or `uv run python scripts/harvest.py run --limit 1`) to
  regenerate `parsed.json` without re-executing the API call.

## Operational Notes

- Concurrency is intentionally serial—plan for ~1 request/minute throughput.
- The executor writes both `response.json` and `structured.json`; prefer the
  latter where possible because it already conforms to the schema.
- All cost/usage telemetry is preserved in `response.json`. Harvest copies the
  fields into `parsed.json` for downstream consumption.

## Migration from CLI

- The old `AnthropicCliExecutor` and local Claude binary dependency were removed.
- Troubleshooting now focuses on API credentials and SDK behaviour (see
  `docs/ANTHROPIC_CLI_TROUBLESHOOTING.md`).
- Makefile and helper scripts no longer call out to `/Users/arun/.claude/local/claude`.

This setup keeps Anthropic aligned with the rest of the provider architecture
while avoiding the brittleness of CLI automation.
