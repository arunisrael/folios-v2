#!/usr/bin/env python3
"""List the 16 strategies scheduled for a given weekday (defaults to today)."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from folios_v2.cli.deps import get_container

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

app = typer.Typer(help="Show strategies assigned to the daily batch rotation")
console = Console()


def _resolve_target_date(target: str | None) -> date:
    if not target:
        return datetime.now(UTC).date()
    try:
        return date.fromisoformat(target)
    except ValueError as exc:
        raise typer.BadParameter("Date must be ISO formatted (YYYY-MM-DD)") from exc


def _weekday_number(target: date) -> int:
    weekday = target.isoweekday()  # 1=Monday .. 7=Sunday
    if weekday > 5:
        raise typer.BadParameter(
            f"{target.isoformat()} is a weekend. Choose a weekday or override with --force-weekday."
        )
    return weekday


async def _fetch_strategies(weekday: int) -> list[tuple[str, str]]:
    container = get_container()
    async with container.unit_of_work_factory() as uow:
        cursor = await uow._session.execute(
            text(
                """
                SELECT s.id, s.name
                FROM strategy_schedules ss
                JOIN strategies s ON s.id = ss.strategy_id
                WHERE ss.weekday = :weekday
                  AND s.status = 'active'
                ORDER BY s.name
                """
            ),
            {"weekday": weekday},
        )
        return [(row.id, row.name) for row in cursor.fetchall()]


def _render_table(rows: Iterable[tuple[str, str]]) -> None:
    table = Table(title="Scheduled Strategies", show_lines=False)
    table.add_column("Strategy ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="magenta")
    for sid, name in rows:
        table.add_row(sid, name)
    console.print(table)


_TARGET_DATE_OPTION = typer.Option(
    None,
    help="ISO date (YYYY-MM-DD). Defaults to today in UTC.",
)
_FORCE_WEEKDAY_OPTION = typer.Option(
    None,
    min=1,
    max=5,
    help="Override weekday number (1=Mon … 5=Fri). Takes precedence over --target-date.",
)
_QUIET_OPTION = typer.Option(
    False,
    "--quiet",
    help="Suppress table output and only print IDs.",
)


@app.command()
def run(
    target_date: str | None = _TARGET_DATE_OPTION,
    force_weekday: int | None = _FORCE_WEEKDAY_OPTION,
    quiet: bool = _QUIET_OPTION,
) -> None:
    """Print the strategies assigned to today's batch rotation."""

    if force_weekday is not None:
        weekday = force_weekday
        target = None
    else:
        target = _resolve_target_date(target_date)
        weekday = _weekday_number(target)

    rows = asyncio.run(_fetch_strategies(weekday))

    if not rows:
        typer.echo("No strategies scheduled for the requested weekday.")
        raise typer.Exit(code=1)

    if quiet:
        for sid, _ in rows:
            typer.echo(sid)
    else:
        label = f"Weekday {weekday}"
        if target is not None:
            label += f" ({target.isoformat()})"
        console.print(f"\n[bold]{label}[/bold]\n")
        _render_table(rows)
        console.print(
            "\nExport IDs with `scripts/get_today_strategies.py --quiet` "
            "or pass them directly to submit_batch_requests."
        )


if __name__ == "__main__":  # pragma: no cover
    app()
