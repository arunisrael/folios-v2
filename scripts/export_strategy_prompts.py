#!/usr/bin/env python3
"""Export strategy prompts for human review (e.g., Anthropic analysts)."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.markdown import Markdown
from sqlalchemy import text

from folios_v2.cli.deps import get_container
from folios_v2.domain import Strategy
from folios_v2.domain.types import StrategyId

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

console = Console()
app = typer.Typer(help="Export strategy prompts for external analysis workflows")


def _resolve_weekday(source_date: str | None, override: int | None) -> int | None:
    if override is not None:
        if not (1 <= override <= 5):
            raise typer.BadParameter("Weekday override must be between 1 (Mon) and 5 (Fri)")
        return override
    if source_date is None:
        return None
    try:
        dt = date.fromisoformat(source_date)
    except ValueError as exc:
        raise typer.BadParameter("Date must be ISO formatted (YYYY-MM-DD)") from exc
    weekday = dt.isoweekday()
    if weekday > 5:
        raise typer.BadParameter("Provided date falls on a weekend; specify --weekday to override.")
    return weekday


async def _strategies_for_weekday(weekday: int) -> list[str]:
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        cursor = await uow._session.execute(
            text(
                """
                SELECT s.id
                FROM strategy_schedules ss
                JOIN strategies s ON s.id = ss.strategy_id
                WHERE ss.weekday = :weekday
                  AND s.status = 'active'
                ORDER BY s.name
                """
            ),
            {"weekday": weekday},
        )
        return [row.id for row in cursor.fetchall()]


def _read_strategy_ids(path: Path) -> list[str]:
    if not path.exists():
        raise typer.BadParameter(f"Strategy file not found: {path}")
    results: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        token = raw.split("#", 1)[0].strip()
        if token:
            results.append(token)
    return results


async def _load_strategies(strategy_ids: Iterable[str]) -> list[Strategy]:
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        repo = uow.strategy_repository
        strategies: list[Strategy] = []
        missing: list[str] = []
        for raw in strategy_ids:
            try:
                sid = StrategyId(raw)
            except ValueError as exc:
                raise typer.BadParameter(f"Invalid UUID for strategy: {raw}") from exc
            strategy = await repo.get(sid)
            if strategy is None:
                missing.append(raw)
            else:
                strategies.append(strategy)

    if missing:
        raise typer.BadParameter("Strategies not found: " + ", ".join(missing))

    strategies.sort(key=lambda s: s.name.lower())
    return strategies


@dataclass
class StrategyExport:
    strategy_id: str
    name: str
    tickers: list[str]
    prompt: str


def _as_markdown(items: list[StrategyExport]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(items, 1):
        lines.append(f"### Strategy {idx}: {item.name}")
        lines.append(f"- **Strategy ID:** `{item.strategy_id}`")
        lines.append(f"- **Tickers:** {', '.join(item.tickers) if item.tickers else '(none)'}")
        lines.append("")
        lines.append("```")
        lines.append(item.prompt.strip())
        lines.append("```")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _write_output(content: str, output: Path | None) -> None:
    if output is None:
        console.print(content)
    else:
        output.write_text(content, encoding="utf-8")
        console.print(f"[green]Wrote export to {output}[/green]")


_WEEKDAY_OPTION = typer.Option(
    None,
    min=1,
    max=5,
    help="Include strategies assigned to this weekday (1=Mon … 5=Fri)",
)
_DATE_HINT_OPTION = typer.Option(
    None,
    help="ISO date to infer weekday from (only used if --weekday is omitted)",
)
_STRATEGY_IDS_OPTION = typer.Option(
    None,
    help="Comma-separated strategy IDs to include",
)
_STRATEGY_FILE_OPTION = typer.Option(
    None,
    help="File containing strategy IDs (one per line, '#' comments allowed)",
)
_OUTPUT_OPTION = typer.Option(
    None,
    help="Optional file path to write the export (defaults to stdout)",
)
_FORMAT_OPTION = typer.Option(
    "markdown",
    case_sensitive=False,
    help="Output format: markdown (default) or json",
)


@app.command()
def run(
    weekday: int | None = _WEEKDAY_OPTION,
    date_hint: str | None = _DATE_HINT_OPTION,
    strategy_ids: str | None = _STRATEGY_IDS_OPTION,
    strategy_file: Path | None = _STRATEGY_FILE_OPTION,
    output: Path | None = _OUTPUT_OPTION,
    format: str = _FORMAT_OPTION,
) -> None:
    """Export prompts for a set of strategies."""

    requested_ids: list[str] = []

    if strategy_ids:
        requested_ids.extend([token.strip() for token in strategy_ids.split(",") if token.strip()])

    if strategy_file:
        requested_ids.extend(_read_strategy_ids(strategy_file))

    weekday_inferred = _resolve_weekday(date_hint, weekday)
    if weekday_inferred is not None:
        requested_ids.extend(asyncio.run(_strategies_for_weekday(weekday_inferred)))

    if not requested_ids:
        # Default to today's weekday in UTC
        today_weekday = datetime.now(UTC).isoweekday()
        if today_weekday > 5:
            raise typer.BadParameter(
                "Today is a weekend. Specify --weekday or provide explicit strategy IDs."
            )
        requested_ids.extend(asyncio.run(_strategies_for_weekday(today_weekday)))

    strategies = asyncio.run(_load_strategies(requested_ids))
    exports = [
        StrategyExport(
            strategy_id=str(strategy.id),
            name=strategy.name,
            tickers=list(strategy.tickers),
            prompt=strategy.prompt,
        )
        for strategy in strategies
    ]

    if format.lower() == "json":
        content = json.dumps([asdict(item) for item in exports], indent=2)
        _write_output(content, output)
        return
    if format.lower() != "markdown":
        raise typer.BadParameter("Unsupported format. Use 'markdown' or 'json'.")

    markdown = _as_markdown(exports)
    if output is None:
        console.print(Markdown(markdown))
    else:
        _write_output(markdown, output)


if __name__ == "__main__":  # pragma: no cover
    app()
