# Strategy Import Plan (folios-py ➜ folios-v2)

## Goal
Migrate the 70 existing strategy definitions (and optional metadata) from the legacy Folios Python SQLite database (`folios-py/development.db`) into the new Folios v2 SQLite persistence layer. Each imported strategy should be compatible with the v2 domain model, scheduled appropriately, and ready for batch/CLI provider execution.

## Source Overview
- Database: `../folios-py/development.db`
- Relevant tables:
  * `strategies`: core definition (id, name, prompt, tickers, risk controls, schedule, metadata)
  * `strategy_provider_portfolios`, `positions`, `orders` (optional, provider-specific data; consider separate migration pass)

## Target Overview
- v2 persistence: `folios-v2` uses async SQLAlchemy with JSON payload columns
  * `Strategy` domain model in `src/folios_v2/domain/strategy.py`
  * Repositories: `SQLiteStrategyRepository`, `SQLiteStrategyScheduleRepository`
  * Unit of work factory: `create_sqlite_unit_of_work_factory(database_url)` writes to SQLite and runs migrations on first use

## Migration Strategy
1. **Extract**
   - Use Python/SQLite3 to read all rows from `strategies`
   - Capture fields: `id`, `name`, `prompt`, `tickers`, `risk_controls`, `metadata`, `schedule`, flags (`options_enabled`, etc.)

2. **Transform**
   - Map string/JSON fields into the v2 `Strategy` model:
     * `tickers`: convert legacy list to tuple of upper-cased strings
     * `risk_controls`: ensure JSON matches v2 `RiskControls` schema
     * `metadata`: map to `StrategyMetadata` (description, time horizon, etc.)
     * `schedule`: convert cron-like string to weekday (1-5) and set optional `research_time_utc`
     * Derive `status` (`active` if `is_active`; `draft` otherwise)
     * Set `preferred_providers` default (e.g., OpenAI prioritized)
     * Set `active_modes` default (batch + CLI)

3. **Load**
   - Instantiate v2 container/unit of work pointing to target DB (e.g., `folios_v2.db`)
   - For each transformed strategy:
     * `strategy_repository.upsert(strategy)`
     * `schedule_repository.upsert(schedule)` (map weekday/time)
   - Commit in batches for performance (optionally 10 at a time)

4. **Validation**
   - After import run `list_strategies` CLI command to confirm entries
   - Optionally generate summary report (count by status, providers)

## Implementation Outline
- Create `scripts/import_strategies.py` with Typer CLI (e.g., `uv run python scripts/import_strategies.py --source ../folios-py/development.db --target folios_v2.db`)
- Steps inside script:
  1. Load source rows via sqlite3 (synchronous OK since this is offline operation)
  2. Map rows into `Strategy` + `StrategySchedule`
  3. For each item, use `asyncio.run` to insert via `SQLiteUnitOfWork`
- Provide dry-run (`--preview`) option to dump JSON without writing

## Edge Cases & Considerations
- Ensure strategy IDs remain unique; retain legacy IDs if possible
- Handle nullable fields (e.g., risk controls may be null -> apply defaults)
- If schedules include weekend/cron entries, map to valid weekday or log/skip
- Confirm timezone assumptions (`schedule` field may encode time-of-day)
- If legacy metadata has provider-specific settings, decide whether to carry them into v2 metadata

## Post-Migration Tasks
- Trigger `harvest` or `submit-stale` scripts to generate initial requests for imported strategies
- Optionally import historical positions/orders in a second phase using the same pattern (mapping to `Position`, `Order`, `PortfolioAccount`)

