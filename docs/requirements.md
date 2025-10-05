# Folios v2 – Requirements Capture

## Source Material Reviewed
- Legacy implementation in `../folios-py/`
  - `batch/manager.py`, `batch/file_handler.py`, `batch/result_processor.py`
  - `cli/` command groups for research, batch, portfolio operations
  - `services/service_container.py` wiring batch manager, providers, database
  - `database/` SQLite models and persistence helpers
  - `analysis/ResponseParser`, `portfolio/` execution engine
- Redesign docs under `../folios-py/docs/redesign/`
  - `system_architecture.md`
  - `provider_plugin_contract.md`
  - `weekly_ops_playbook.md`

## Core Business Goals
- Keep Folios as a local-first research + execution workbench backed by SQLite.
- Support multiple AI providers with both batch API and CLI execution paths.
- Normalize provider onboarding through declarative plugins describing capabilities, throttling, serializers, and parsers.
- Enforce a weekly operating cadence:
  - Research spread Tue–Sat via scheduler.
  - Single execution window per strategy at Monday market open with holiday awareness.
  - Structured Sunday outlook and Friday recap emails.
- Maintain determinism by enforcing canonical JSON schemas across providers.

## Key Domain Entities (new design)
- `ProviderPlugin`: declares provider metadata, supported execution modes, executors, serializer, parser, and config schema.
- `ExecutionMode`: enum covering `batch`, `cli`, and future `hybrid` flows.
- `Strategy`: retains prompt/ticker/risk details plus scheduling metadata (`research_day`, `preferred_providers`, `active_modes`, etc.).
- `StrategySchedule`: persists weekday assignment and next-run timestamps for cron drivers.
- `StrategyRun`: tracks weekly cycle per strategy (`week_of`, linked research/execution requests, status, snapshots).
- `Request`: unified lifecycle for research/execution/email prep work with timestamps, mode, payload references, and lifecycle state.
- `ExecutionTask`: concrete units (batch job or CLI invocation) with provider job IDs, exit codes, retries, and artifacts directory.
- `LifecycleState`: shared state machine bridging requests and execution tasks (`pending` → `scheduled` → … → `succeeded`/`failed`).
- Supporting tables: `EmailDigest`, `PositionSnapshot`, reuse of proposals/orders/positions from v1.

## Layered Architecture Targets
- **Domain layer (`folios_v2.domain`)**: strict dataclasses / typed models for strategies, requests, tasks, schedules, digests, etc.
- **Persistence layer (`folios_v2.persistence`)**: repository interfaces + SQLite implementations (SQLAlchemy or raw SQL) for domain aggregates, with unit-testable abstractions.
- **Provider layer (`folios_v2.providers`)**: plugin registry, shared protocols, concrete adapters (OpenAI, Anthropic, Gemini, CLI shells) with serializers/parsers.
- **Runtime layer (`folios_v2.runtime`)**: async batch runtime (submission/poll/download) and CLI runtime (subprocess execution, logging, retries).
- **Orchestration (`folios_v2.orchestration`)**: strategy coordinator, request orchestrator, lifecycle engine enforcing scheduling/holiday constraints.
- **Scheduling (`folios_v2.scheduling`)**: cron entry scripts, spacing algorithm, load balancing utilities.
- **Notifications (`folios_v2.notifications`)**: email digest generation (Jinja templates + persistence) and optional Slack hooks.
- **CLI (`folios_v2.cli`)**: Typer/Click commands for strategy sync, scheduler status, request operations, digests.
- **Service container (`folios_v2.container`)**: composition root wiring config, repositories, orchestrators, runtimes, and provider registry.

## Technical Expectations for v2
- Strict typing with `mypy --strict` discipline; prefer `pydantic` v2 models or frozen dataclasses for validation.
- Async-first execution runtimes; orchestrators coordinate via asyncio tasks with explicit rate limiting.
- Configuration via typed settings objects (e.g., `pydantic-settings` or dataclass-based loader) supporting environment overrides.
- Unit tests covering domain models, provider plugin contracts, runtimes, and orchestration flows using fixtures/mocks.
- Tooling parity: `ruff`, `black`, `mypy`, `pytest`, and `uv`/`hatchling` build support.
- SQLite schema migrations via Alembic or manual SQL migration scripts with idempotent apply helpers.

## Scope Notes & Open Questions
- Need to decide on ORM (SQLAlchemy 2.0) vs. lightweight query layer; legacy uses SQLAlchemy models + manual helpers.
- Email delivery in v1 is minimal; redesign expects structured digest generator — can be stubbed initially with file writes + interface for SMTP/SendGrid.
- Determine CLI framework (Click in v1). Typer may offer better typing ergonomics but Click is battle-tested.
- Evaluate how much of portfolio execution engine to port vs. wrap existing modules from v1 (analysis/portfolio directories may be reusable with adjustments).

This document anchors the v2 rebuild plan and will evolve as we refine scope during implementation phases.
