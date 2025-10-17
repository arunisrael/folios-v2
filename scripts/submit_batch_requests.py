"""Submit batch research requests for strategies."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from pathlib import Path
from typing import NamedTuple

import typer
from dotenv import load_dotenv
from sqlalchemy import text

from folios_v2.cli.deps import get_container
from folios_v2.domain import ExecutionMode, RequestPriority, RequestType, Strategy
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.types import StrategyId
from folios_v2.utils import utc_now

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

app = typer.Typer(help="Submit batch research requests for strategies")

ALLOWED_PROVIDERS = {"openai", "gemini", "anthropic"}


class SubmissionResult(NamedTuple):
    strategy: Strategy
    provider: ProviderId
    request_id: str
    task_id: str


def _read_strategy_file(path: Path) -> list[str]:
    if not path.exists():
        raise typer.BadParameter(f"Strategy file not found: {path}")
    results: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        token = raw.split("#", 1)[0].strip()
        if token:
            results.append(token)
    return results


def _collect_strategy_ids(
    strategy_id: str | None,
    strategy_ids: str | None,
    strategy_file: Path | None,
) -> set[str]:
    values: set[str] = set()
    if strategy_id:
        values.add(strategy_id.strip())
    if strategy_ids:
        for token in strategy_ids.split(","):
            token = token.strip()
            if token:
                values.add(token)
    if strategy_file:
        values.update(_read_strategy_file(strategy_file))
    return values


async def _load_strategies(strategy_ids: set[str]) -> list[Strategy]:
    """Resolve strategy identifiers to Strategy models."""

    container = get_container()
    async with container.unit_of_work_factory() as uow:
        repo = uow.strategy_repository
        if not strategy_ids:
            strategies = list(await repo.list_active())
            return sorted(strategies, key=lambda s: s.name.lower())

        resolved: list[Strategy] = []
        missing: list[str] = []
        for raw_id in sorted(strategy_ids):
            try:
                sid = StrategyId(raw_id)
            except ValueError as exc:
                raise typer.BadParameter(f"Invalid UUID for strategy: {raw_id}") from exc

            strategy = await repo.get(sid)
            if strategy is None:
                missing.append(raw_id)
            else:
                resolved.append(strategy)

        if missing:
            raise typer.BadParameter("Strategies not found: " + ", ".join(missing))

        return sorted(resolved, key=lambda s: s.name.lower())


def _parse_providers(tokens: Iterable[str]) -> list[ProviderId]:
    providers: list[ProviderId] = []
    seen: set[str] = set()
    for token in tokens:
        provider = token.strip().lower()
        if not provider:
            continue
        if provider not in ALLOWED_PROVIDERS:
            raise typer.BadParameter(
                f"Unsupported provider '{provider}'. Allowed: "
                + ", ".join(sorted(ALLOWED_PROVIDERS))
            )
        if provider in seen:
            continue
        providers.append(ProviderId(provider))
        seen.add(provider)
    if not providers:
        raise typer.BadParameter("At least one provider must be specified")
    return providers


async def _submit_batch_requests(
    strategies: list[Strategy],
    providers: list[ProviderId],
) -> list[SubmissionResult]:
    """Submit batch research requests for the supplied strategies."""

    container = get_container()
    submitted: list[SubmissionResult] = []

    async with container.unit_of_work_factory() as uow:
        if not strategies:
            typer.echo("No strategies matched the requested filters")
            return submitted

        typer.echo(
            f"Submitting batch requests for {len(strategies)} strategy(ies) "
            f"across providers: {', '.join(p.value for p in providers)}"
        )

        for strategy in strategies:
            typer.echo(f"\nStrategy: {strategy.name} ({strategy.id})")

            for provider in providers:
                try:
                    plugin = container.provider_registry.require(provider, ExecutionMode.BATCH)
                except Exception as exc:  # pragma: no cover - defensive
                    typer.echo(f"  Skipping {provider.value}: {exc}", err=True)
                    continue

                if not plugin.supports_batch:
                    typer.echo(f"  Skipping {provider.value}: batch mode not supported")
                    continue

                request, task = await container.request_orchestrator.enqueue_request(
                    strategy,
                    provider_id=provider,
                    request_type=RequestType.RESEARCH,
                    mode=ExecutionMode.BATCH,
                    priority=RequestPriority.NORMAL,
                    scheduled_for=utc_now(),
                    metadata={"triggered_by": "submit_batch_requests"},
                )

                typer.echo(f"  ✓ {provider.value}: request_id={request.id}, task_id={task.id}")
                submitted.append(
                    SubmissionResult(
                        strategy=strategy,
                        provider=provider,
                        request_id=str(request.id),
                        task_id=str(task.id),
                    )
                )

        await uow.commit()

    typer.echo(f"\n{'='*60}")
    typer.echo(f"Total batch requests submitted: {len(submitted)}")
    typer.echo(f"{'='*60}")
    return submitted


def _strategies_from_weekday(weekday: int) -> list[str]:
    """Return strategy IDs assigned to a weekday via schedule repository."""

    container = get_container()
    async def _query() -> list[str]:
        async with container.unit_of_work_factory() as uow:
            cursor = await uow._session.execute(
                text(
                    """
                    SELECT ss.strategy_id
                    FROM strategy_schedules ss
                    JOIN strategies s ON s.id = ss.strategy_id
                    WHERE ss.weekday = :weekday
                      AND s.status = 'active'
                    ORDER BY s.name
                    """
                ),
                {"weekday": weekday},
            )
            return [row.strategy_id for row in cursor.fetchall()]

    return asyncio.run(_query())


_STRATEGY_ID_OPTION = typer.Option(
    None,
    help="Single strategy ID (deprecated; use --strategy-ids/--strategy-file/--weekday)",
)
_STRATEGY_IDS_OPTION = typer.Option(
    None,
    help="Comma-separated list of strategy IDs to submit",
)
_STRATEGY_FILE_OPTION = typer.Option(
    None,
    help="File containing strategy IDs (one per line, '#' comments allowed)",
)
_WEEKDAY_OPTION = typer.Option(
    None,
    min=1,
    max=5,
    help="Select all strategies scheduled for the given weekday (1=Mon … 5=Fri)",
)
_PROVIDERS_OPTION = typer.Option(
    "openai,gemini",
    help="Comma-separated provider IDs (openai, gemini, anthropic)",
)


@app.command()
def run(
    strategy_id: str | None = _STRATEGY_ID_OPTION,
    strategy_ids: str | None = _STRATEGY_IDS_OPTION,
    strategy_file: Path | None = _STRATEGY_FILE_OPTION,
    weekday: int | None = _WEEKDAY_OPTION,
    providers: str = _PROVIDERS_OPTION,
) -> None:
    """Submit batch research requests for strategies."""

    provider_list = _parse_providers(providers.split(","))

    requested_ids = _collect_strategy_ids(strategy_id, strategy_ids, strategy_file)
    if weekday is not None:
        requested_ids.update(_strategies_from_weekday(weekday))

    strategies = asyncio.run(_load_strategies(requested_ids))
    asyncio.run(_submit_batch_requests(strategies, provider_list))


if __name__ == "__main__":  # pragma: no cover
    app()
