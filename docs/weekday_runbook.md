# Weekday Research & Execution Runbook

This is the canonical playbook for Folios v2 weekday operations.  
Follow these steps exactly so future agents do not create ad‑hoc scripts.

## 0. Environment Prep
```bash
cd /Users/arun/apps/folios-v2
set -a; source .env; set +a
```

## 1. Harvest Yesterday’s Batches
```bash
make poll-batch-status          # optional snapshot
make harvest-batch-results      # downloads + parses OpenAI/Gemini results
```

## 2. Load Today’s 16 Strategies
```bash
uv run python scripts/get_today_strategies.py
# Quiet mode for downstream scripting:
uv run python scripts/get_today_strategies.py --quiet > today_strategies.txt
```

## 3. Queue New Batch Requests (OpenAI + Gemini)
```bash
uv run python scripts/submit_batch_requests.py \
  --strategy-file today_strategies.txt \
  --providers openai,gemini
```
> `submit_batch_requests.py` now accepts `--strategy-ids`, `--strategy-file`, and  
> `--weekday` (1=Mon … 5=Fri). Use these instead of hard-coded helper scripts.

## 4. Submit Batch Jobs to Providers
```bash
make submit-batch-jobs PROVIDERS="openai,gemini"
```

## 5. Prepare Claude / Anthropic Analysis
1. Export prompts for the same strategy set:
   ```bash
   uv run python scripts/export_strategy_prompts.py \
     --strategy-file today_strategies.txt \
     --format markdown \
     --output tmp/anthropic_prompts.md
   ```
2. Share `tmp/anthropic_prompts.md` with the Anthropic analyst/agent.
3. Analyst pastes completed research into `ANTHROPIC_RECOMMENDATIONS.md`.

## 6. Apply Anthropic Recommendations
```bash
uv run python scripts/apply_anthropic_recommendations.py
```

## 7. Execute Completed AI Recommendations
```bash
uv run python scripts/execute_ready.py --providers "openai,gemini" --limit 16
```
> Increase `--limit` if multiple days are queued.

## 8. Post-Run Verification
```bash
make status
uv run python scripts/check_portfolios.py      # optional QA
```

---

## Canonical Script Reference

| Task | Script / Command | Notes |
| --- | --- | --- |
| Harvest batch + CLI results | `make harvest-batch-results` | Uses `harvest.py` |
| Poll provider queues | `make poll-batch-status` | `check_batch_status.py` + `check_gemini_batch.py` |
| Select today’s strategies | `scripts/get_today_strategies.py` | 16 per weekday schedule |
| Submit research requests | `scripts/submit_batch_requests.py` | Accepts `--strategy-file`, `--strategy-ids`, `--weekday` |
| Submit queued jobs | `scripts/submit_batch_jobs.py` | Providers: openai, gemini |
| Export prompts for humans | `scripts/export_strategy_prompts.py` | Markdown or JSON |
| Apply Anthropic recs | `scripts/apply_anthropic_recommendations.py` | Reads `ANTHROPIC_RECOMMENDATIONS.md` |
| Execute trades | `scripts/execute_ready.py` | Wraps `execute_recommendations.py` |
| Diagnostics | `check_batch_status.py`, `check_gemini_batch.py`, `list_gemini_batches.py`, `show_status.py`, `check_portfolios.py` | |

**Removed legacy scripts:**  
`execute_10_random_anthropic.py`, `execute_10_random_inline.py`, `execute_all_recommendations.py`, `execute_remaining_anthropic.py`, `harvest_gemini_batches.py`, `harvest_gemini_simple.py`, `monitor_and_harvest_loop.py`, `run_10_strategies_cli.py`, `run_cli_test.py`, `run_single_strategy.py`, `run_strategies_batch.py`, `run_strategies_cli.py`, `select_unrun_cli_strategies.py`, `select_unrun_strategies.py`, `submit_pending_batches.py`.  
Do **not** recreate these; the canonical tools above cover their functionality.

---

## Tips
- When sharing IDs between steps, use `--quiet` output to avoid formatting overhead.
- All new scripts auto-load `.env`; no additional setup needed.
- For ad-hoc subsets, provide `--strategy-ids` to both `submit_batch_requests.py` and `export_strategy_prompts.py` so Anthropic receives matching prompts.
