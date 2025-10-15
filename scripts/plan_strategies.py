"""Show strategies that need fresh research submissions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
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

console = Console()
app = typer.Typer(help="Plan which strategies require new research runs")


async def _collect_candidates(max_age_hours: int, providers: list[str]) -> list[dict[str, str]]:
    container = get_container()
    cutoff = datetime.now(UTC) - timedelta(hours=max_age_hours)

    allowed_providers = {"openai", "gemini", "anthropic"}
    filtered = [p for p in providers if p in allowed_providers]
    provider_filters = " OR ".join(
        f"r.provider_id = :p{i}" for i in range(len(filtered))
    )
    provider_params = {f"p{i}": provider for i, provider in enumerate(filtered)}
    where_provider = f"AND ({provider_filters})" if filtered else ""

    query = text(
        f"""
        SELECT
            s.id,
            s.name,
            s.status,
            COALESCE(
                (
                    SELECT MAX(r.created_at)
                    FROM requests r
                    WHERE r.strategy_id = s.id
                      AND r.request_type = 'research'
                      {where_provider}
                ),
                ''
            ) AS last_request_at,
            (
                SELECT COUNT(*)
                FROM requests r
                WHERE r.strategy_id = s.id
                  AND r.lifecycle_state IN ('pending', 'scheduled', 'running', 'awaiting_results')
                  {where_provider}
            ) AS active_requests
        FROM strategies s
        WHERE s.status = 'active'
        ORDER BY last_request_at NULLS FIRST, s.name
        """  # noqa: S608
    )

    async with container.unit_of_work_factory() as uow:
        cursor = await uow._session.execute(query, provider_params)
        rows = cursor.fetchall()

    candidates: list[dict[str, str]] = []
    for row in rows:
        last_at = row.last_request_at
        if not last_at:
            candidates.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "last_request_at": "never",
                    "active_requests": str(row.active_requests),
                }
            )
            continue

        # SQLite returns naive timestamp; parse in UTC
        last_dt = datetime.fromisoformat(last_at)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=UTC)
        if last_dt < cutoff or row.active_requests == 0:
            candidates.append(
                {
                    "id": row.id,
                    "name": row.name,
                    "last_request_at": last_dt.isoformat(),
                    "active_requests": str(row.active_requests),
                }
            )
    return candidates


@app.command()
def run(
    max_age_hours: int = typer.Option(
        48, help="Consider strategies stale after this many hours"
    ),
    providers: str = typer.Option(
        "openai,gemini,anthropic", help="Comma separated provider filter"
    ),
) -> None:
    """Print strategies that should receive new research submissions."""

    allowed_providers = {"openai", "gemini", "anthropic"}
    provider_list = [
        p.strip()
        for p in providers.split(",")
        if p.strip() and p.strip() in allowed_providers
    ]
    candidates = asyncio.run(_collect_candidates(max_age_hours, provider_list))

    if not candidates:
        console.print("[green]All active strategies have recent activity.[/green]")
        return

    table = Table(title="Strategies Needing Research")
    table.add_column("Strategy ID", style="cyan", no_wrap=True)
    table.add_column("Name", style="magenta")
    table.add_column("Last Research", style="yellow")
    table.add_column("Active Requests", style="green")

    for item in candidates:
        table.add_row(
            item["id"],
            item["name"],
            item["last_request_at"],
            item["active_requests"],
        )

    console.print(table)
    console.print(
        "\nUse `make enqueue-strategies` followed by the staged batch commands "
        "to process the listed strategies."
    )


if __name__ == "__main__":  # pragma: no cover
    app()
