"""Execute portfolios for requests that have completed research."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from folios_v2.cli.deps import get_container
from folios_v2.domain import LifecycleState
from scripts.execute_recommendations import execute_request

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

console = Console()
app = typer.Typer(help="Execute recommendations for completed research requests")


async def _load_ready_requests(
    providers: list[str], limit: int
) -> Sequence[tuple[str, str, str]]:
    container = get_container()

    query = text(
        """
        SELECT id, strategy_id, provider_id
        FROM requests
        WHERE lifecycle_state = :state
          AND request_type = 'research'
        ORDER BY completed_at
        LIMIT :limit
        """
    )

    async with container.unit_of_work_factory() as uow:
        cursor = await uow._session.execute(
            query,
            {"state": LifecycleState.SUCCEEDED.value, "limit": limit},
        )
        rows = cursor.fetchall()
    return [
        (row.id, row.strategy_id, row.provider_id)
        for row in rows
        if not providers or row.provider_id in providers
    ]


@app.command()
def run(
    providers: str = typer.Option(
        "openai,gemini,anthropic",
        help="Comma separated providers to include",
    ),
    initial_balance: float = typer.Option(100000.0, help="Initial portfolio balance"),
    limit: int = typer.Option(10, help="Maximum number of requests to execute"),
) -> None:
    """Execute recommendations for completed research requests."""

    allowed_providers = {"openai", "gemini", "anthropic"}
    provider_list = [
        p.strip()
        for p in providers.split(",")
        if p.strip() and p.strip() in allowed_providers
    ]
    ready = asyncio.run(_load_ready_requests(provider_list, limit))

    if not ready:
        console.print("[yellow]No completed requests awaiting execution.[/yellow]")
        return

    table = Table(title="Execution Results")
    table.add_column("Request ID", style="cyan", no_wrap=True)
    table.add_column("Strategy ID", style="magenta", no_wrap=True)
    table.add_column("Provider", style="green")
    table.add_column("Status", style="yellow")

    for request_id, strategy_id, provider_id in ready:
        console.print(
            f"Executing request {request_id} ({provider_id}) for strategy {strategy_id}"
        )
        try:
            asyncio.run(
                execute_request(
                    request_id=request_id,
                    strategy_id=strategy_id,
                    provider_id=provider_id,
                    initial_balance=initial_balance,
                )
            )
            status = "executed"
        except Exception as exc:  # pragma: no cover - defensive
            status = f"failed: {exc}"
        table.add_row(request_id, strategy_id, provider_id, status)

    console.print(table)
    console.print("\nVerify portfolio balances via analytics queries or dashboards.")


if __name__ == "__main__":  # pragma: no cover
    app()
