# Real Batch Execution Migration Plan

## Context
- Goal: replace simulated batch responses in `folios-v2` with real provider API executions while reusing patterns that worked in `folios-py`.
- Scope: OpenAI, Gemini, and Anthropic batch workflows spanning serialization, submission, polling, download, parsing, persistence, and orchestration.
- Out of scope: CLI execution path (Codex/Gemini CLI) and downstream research synthesis beyond storing structured outputs.

## What Worked in @folios-py
- **Lifecycle orchestration** – `batch/manager.py:38` coordinates queue → submit → poll → download → process and caches provider adapters.
- **Input generation** – `batch/file_handler.py:20` builds provider-specific JSONL/JSON envelopes with custom IDs and schema metadata.
- **Provider adapters** – `batch/providers/openai_batch.py:24` and `.../gemini_batch.py:19` encapsulate real API clients, status mapping, downloads, and cancellation.
- **Job monitoring** – `batch/job_tracker.py:20` asynchronously polls, enforces timeouts, and triggers retries.
- **Result ingestion** – `batch/result_processor.py:22` parses provider payloads, updates request/job records, and seeds follow-on research artifacts.

## Current State in @folios-v2
- **Simulation plumbing** – Provider plugins wire the `LocalJSON*` serializer/executor/parser combo (`src/folios_v2/providers/openai/plugin.py:15`, `.../gemini/plugin.py:15`).
- **Runtime limitations** – `src/folios_v2/runtime/batch.py:15` blocks on synchronous polling loops with fixed budgets; no persisted status transitions.
- **Harvest pipeline** – `scripts/harvest.py:21` writes `parsed.json`, marks tasks `SUCCEEDED`, but lacks provider job metadata and structured payload storage.
- **Persistence model** – `src/folios_v2/domain/request.py:73` exposes `provider_job_id`, `stdout_path`, etc., yet they remain unset through the current flow.
- **Configuration gaps** – `src/folios_v2/config.py:14` provides no API key slots or batch tuning knobs needed for real clients.

## Target Architecture
1. **Provider Integrations**
   - Implement dedicated modules per provider (`src/folios_v2/providers/{provider}/batch.py`).
   - Responsibilities: request serialization (JSON schema, prompts, custom IDs), submission via official SDK/REST, status polling, download, result parsing, cancellation.
   - Mirror v1 adapters but align with v2 domain models and error classes.
2. **Runtime & Monitoring**
   - Extend `BatchRuntime` to:
     - Persist `SubmitResult.provider_job_id` into `ExecutionTask(provider_job_id)` and update `LifecycleState` to `AWAITING_RESULTS`.
     - Emit status events to a new `BatchMonitor` service that polls asynchronously (akin to v1 `JobTracker`).
   - Introduce configurable poll intervals/timeouts per provider via settings.
3. **Persistence Enhancements**
   - Add tables or columns for batch jobs if required (e.g., `provider_job_id`, `status`, `result_path`, metadata blobs).
   - Update repositories to read/write provider status, errors, retry counters.
   - Ensure downloads land under `artifacts/<request>/<task>/provider/results.jsonl` for deterministic retrieval.
4. **Result Processing**
   - Create a parser service that:
     - Reads downloaded artifacts, produces canonical structured payloads, and stores them in `Request.payload_ref` or dedicated tables.
     - Updates tasks and requests (`LifecycleState.SUCCEEDED/FAILED`, timestamps, error messages).
     - Optionally triggers downstream orchestration hooks (strategy resume, notifications).
5. **Configuration & Secrets**
   - Extend `AppSettings` with `openai_api_key`, `gemini_api_key`, `anthropic_api_key`, poll intervals, batch sizes.
   - Surface environment variable names (`OPENAI_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) and add validation during container build.
6. **Provider Registry Wiring**
   - Replace `LocalJSON*` components with real adapters when keys are present; optionally retain simulation mode behind a feature flag for local dev.
7. **Operational Tooling**
   - Add CLI commands to submit/poll/list batches, inspect job status, retry failures, and download artifacts for debugging.

## Workstreams & Deliverables
1. **Design & Schema Updates**
   - ERD / migration script for batch job persistence (SQLite + future Postgres).
   - Sequence diagrams documenting submit → monitor → harvest.
2. **Provider Modules**
   - OpenAI batch adapter using `openai.AsyncOpenAI` (`/v1/batches` endpoint).
   - Gemini batch adapter via `google-genai` client (`batches.create` with inline responses).
   - Anthropic adapter targeting `/v1/messages/batch` (or queued sequential fallback if official batch is unavailable).
   - Shared serializer utilities for JSON schema payloads.
3. **Runtime & Monitor**
   - `BatchRuntime` updates, new `BatchMonitor` background task, integration with lifecycle engine.
   - Restart-safe polling that resumes after process restarts using persisted state.
4. **Result Processing**
   - Parser service with provider-specific transformations and structured output validation.
   - Integration with orchestration layer to resume strategy workflows.
5. **Config & Secrets Management**
   - Update `.env.example`, documentation, and container wiring.
6. **Testing & QA**
   - Unit tests: serializers, adapters (mocked HTTP), parser normalization, runtime state transitions.
   - Integration tests: use recorded fixtures to simulate submit/poll/download.
   - Smoke script exercising full cycle against sandbox accounts.
7. **Documentation**
   - Runbook covering credential setup, monitoring dashboards, retry/cancel procedures.
   - Developer README updates describing new CLI commands and artifacts layout.

## Open Questions / Follow-Up
- Do we standardize on JSON schema validation pre-submit to catch prompt/config drift?
- Preferred storage for large provider outputs (local disk vs blob storage) in production?
- Requirements for cost tracking per batch (token usage, pricing tiers)?
- Need for backpressure / throttling beyond provider limits (queue prioritization, concurrency caps)?
- Disaster recovery expectations if monitor or harvest crashes mid-cycle.

## Risks & Mitigations
- **API rate limits** – Configure per-provider throttles, implement exponential backoff, and surface metrics.
- **Credential management** – Separate dev/staging/prod keys, leverage secret stores, validate at startup.
- **Schema drift** – Lock provider payload formats with schema tests; alert when response JSON no longer parses.
- **Long-running jobs** – Enforce timeouts and retries; allow manual cancellation via CLI/API.
- **Data loss** – Persist job states and artifacts before marking tasks complete; checksum downloaded files.

## Rollout Steps
1. Ship provider adapters behind feature flags; run dual-mode where simulation remains default.
2. Enable real batch on staging with OpenAI only; monitor telemetry, success rates, artifact correctness.
3. Expand to Gemini/Anthropic once OpenAI flow is stable.
4. Remove simulation wiring or retain as fallback once confidence is high.

## Owner Handoff Checklist
- [ ] Review DB migration plan and approve schema changes.
- [ ] Confirm environment variable naming with DevOps.
- [ ] Provide sandbox API keys for integration tests.
- [ ] Schedule staging cutover rehearsal.
- [ ] Document monitoring alerts and dashboards.

