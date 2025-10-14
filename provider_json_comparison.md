# Provider JSON Output Comparison – Anthropic Direct vs Gemini CLI vs OpenAI Batch

This note illustrates the artifact structures produced by each provider path after
moving Anthropic to the official SDK. All examples reference real requests executed
in October 2025.

---

## Anthropic (Direct API)

- **Request ID:** `79b9930c-3a6f-4f41-ae9b-a3fa8ec37ef2`
- **Task ID:** `5f1f84b5-424f-4f6d-a66a-9784bf9e6604`
- **Executor:** `AnthropicDirectExecutor`

### Artifact Layout

```
artifacts/79b9930c-3a6f-4f41-ae9b-a3fa8ec37ef2/5f1f84b5-424f-4f6d-a66a-9784bf9e6604/
├── prompt.txt
├── response.json
├── structured.json
└── parsed.json
```

### `response.json`

```json
{
  "provider": "anthropic",
  "prompt": "Analyze AAPL and MSFT for investment potential...",
  "model": "claude-sonnet-4-5-20250929",
  "method": "direct_api",
  "result": "{...large JSON block...}",
  "structured": { "recommendations": [...] },
  "usage": {
    "input_tokens": 3376,
    "output_tokens": 1930,
    "cache_creation_input_tokens": 18085,
    "cache_read_input_tokens": 38031
  },
  "total_cost_usd": 0.6249848,
  "stop_reason": "end_turn",
  "exit_code": 0
}
```

- Token/cost telemetry comes directly from `anthropic.Anthropic.messages.create`.
- `_extract_structured_json` converts the markdown JSON block into the
  `structured` field.

### `structured.json`

```json
{
  "recommendations": [
    {
      "ticker": "MSFT",
      "action": "BUY",
      "allocation_percent": 10.0,
      "confidence": 0.88,
      "rationale": "Azure strength and AI leadership"
    },
    {
      "ticker": "AAPL",
      "action": "HOLD",
      "allocation_percent": 6.0,
      "confidence": 0.75
    }
  ],
  "market_context": {
    "macro": "AI infrastructure spending accelerating"
  }
}
```

### Parser Output (`parsed.json`)

`UnifiedResultParser` merges the structured payload with request metadata:

```json
{
  "provider": "anthropic",
  "request_id": "79b9930c-3a6f-4f41-ae9b-a3fa8ec37ef2",
  "task_id": "5f1f84b5-424f-4f6d-a66a-9784bf9e6604",
  "strategy_id": "877be608-8547-4656-9d16-0f395df434dd",
  "prompt": "Analyze AAPL and MSFT for investment potential...",
  "source": "cli_structured",
  "recommendations": [...],
  "usage": { ... },
  "total_cost_usd": 0.6249848
}
```

### Code Pointers

- Executor: `src/folios_v2/providers/anthropic/direct_executor.py`
- Parser: `src/folios_v2/providers/anthropic/plugin.py`
- Unified renderer: `src/folios_v2/providers/unified_parser.py`

---

## Gemini (CLI)

- **Request ID:** `9d81a050-c698-4ef9-98b4-6b3361e4c045`
- **Task ID:** `0d4293ba-da95-4203-9f4c-8a84ec32b5b6`
- **Executor:** `GeminiCliExecutor`

### Artifact Layout

```
artifacts/9d81a050-c698-4ef9-98b4-6b3361e4c045/0d4293ba-da95-4203-9f4c-8a84ec32b5b6/
├── prompt.txt
├── response.json
├── structured.json (when available)
├── stderr.txt
└── parsed.json
```

### `response.json`

Contains the raw CLI payload with model statistics and tool usage:

```json
{
  "provider": "gemini",
  "command": ["gemini", "--output-format", "json", "-y", "Analyze ..."],
  "exit_code": 0,
  "cli_output": {
    "response": "```json\n{\"recommendations\": [...]}\n```",
    "stats": {
      "models": {
        "gemini-2.5-pro": {"tokens": {"prompt": 23092, "candidates": 97}},
        "gemini-2.5-flash": {"tokens": {"prompt": 4334, "candidates": 864}}
      },
      "tools": {"google_web_search": {"count": 1, "success": 1}}
    }
  },
  "stderr": "Loaded cached credentials.\n"
}
```

### `parsed.json`

`UnifiedResultParser` extracts the JSON block from `cli_output.response`:

```json
{
  "provider": "gemini",
  "request_id": "9d81a050-c698-4ef9-98b4-6b3361e4c045",
  "task_id": "0d4293ba-da95-4203-9f4c-8a84ec32b5b6",
  "strategy_id": "877be608-8547-4656-9d16-0f395df434dd",
  "source": "cli_structured",
  "recommendations": [...]
}
```

### Code Pointers

- Executor: `src/folios_v2/providers/gemini/cli_executor.py`
- Parser: `src/folios_v2/providers/unified_parser.py`

---

## OpenAI (Batch)

- **Request ID:** `57b04394-a704-4151-81d9-203ce3cd1d61`
- **Task ID:** `36df6ed1-300c-423e-a6c0-e35e5509a8ad`
- **Executor:** `OpenAIBatchExecutor` (simulation mode in this dataset)

### Artifact Layout

```
artifacts/57b04394-a704-4151-81d9-203ce3cd1d61/36df6ed1-300c-423e-a6c0-e35e5509a8ad/
├── openai_payload.jsonl
├── openai_batch_results.jsonl
└── parsed.json
```

### `parsed.json`

```json
{
  "provider": "openai",
  "request_id": "57b04394-a704-4151-81d9-203ce3cd1d61",
  "task_id": "36df6ed1-300c-423e-a6c0-e35e5509a8ad",
  "strategy_id": "877be608-8547-4656-9d16-0f395df434dd",
  "source": "batch_jsonl",
  "provider_job_id": "36df6ed1-300c-423e-a6c0-e35e5509a8ad-0bd96b43",
  "recommendations": []
}
```

When real batch results arrive, `UnifiedResultParser` iterates each JSONL line and
collects any embedded `recommendations` arrays.

### Code Pointers

- Executor: `src/folios_v2/providers/openai/batch.py`
- Runtime: `src/folios_v2/runtime/batch.py`
- Harvest integration: `scripts/harvest.py`

---

## Summary of Differences

| Aspect | Anthropic (Direct) | Gemini (CLI) | OpenAI (Batch) |
| --- | --- | --- | --- |
| Transport | HTTPS via SDK | Local CLI process | HTTPS via SDK (async) |
| Artifacts | `response.json`, `structured.json` | `response.json`, optional `structured.json`, `stderr.txt` | `<provider>_payload.jsonl`, `<provider>_batch_results.jsonl` |
| Cost metrics | `total_cost_usd`, token usage | Not provided | Available when using real API |
| Parser source | `structured.json` | `structured.json` or `response` text | Batch JSONL records |
| Turnaround | Immediate | Immediate | 24+ hours |

Understanding these shapes makes it easier to build downstream tooling (portfolio
execution, HTML generation, analytics) without reverse-engineering artifacts on the
fly.
