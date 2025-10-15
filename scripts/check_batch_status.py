"""Check status of OpenAI batch requests."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import httpx
import typer
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from folios_v2.cli.deps import get_container

# Load .env file
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

app = typer.Typer(help="Check OpenAI batch request status")
console = Console()


def _format_timestamp(value: object) -> str:
    """Render timestamps consistently for table output."""

    if not value:
        return "[dim]-[/dim]"
    if isinstance(value, str):
        return value[:19]
    return str(value)


async def _list_openai_batches(limit: int = 100) -> list[dict]:
    """List batch jobs from OpenAI API."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        console.print("[red]Error: OPENAI_API_KEY not found in environment[/red]")
        raise typer.Exit(code=1)

    endpoint = os.getenv("OPENAI_API_BASE", "https://api.openai.com")
    endpoint = endpoint.rstrip("/")

    headers = {"Authorization": f"Bearer {api_key}"}

    async with httpx.AsyncClient(base_url=endpoint, timeout=30.0, headers=headers) as client:
        response = await client.get(f"/v1/batches?limit={limit}")
        response.raise_for_status()
        data = response.json()
        return data.get("data", [])


async def _get_local_batch_status() -> list[dict]:
    """Get batch status from local database."""
    container = get_container()

    async with container.unit_of_work_factory() as uow:
        # Query execution tasks with batch mode
        query = """
            SELECT
                et.id as task_id,
                et.lifecycle_state,
                json_extract(et.payload, '$.provider_job_id') as provider_job_id,
                json_extract(et.payload, '$.metadata.artifact_dir') as artifact_dir,
                json_extract(et.payload, '$.metadata.last_poll_status') as last_poll_status,
                json_extract(et.payload, '$.metadata.last_polled_at') as last_polled_at,
                et.created_at,
                et.updated_at,
                et.started_at,
                et.completed_at,
                r.id as request_id,
                r.provider_id,
                r.strategy_id,
                s.name as strategy_name
            FROM execution_tasks et
            JOIN requests r ON et.request_id = r.id
            LEFT JOIN strategies s ON r.strategy_id = s.id
            WHERE r.mode = 'batch' AND r.provider_id = 'openai'
            ORDER BY et.created_at DESC
        """

        # Use the internal session from the UOW
        cursor = await uow._session.execute(text(query))
        rows = cursor.fetchall()

        results = []
        for row in rows:
            results.append({
                "task_id": row[0],
                "lifecycle_state": row[1],
                "provider_job_id": row[2],
                "artifact_dir": row[3],
                "last_poll_status": row[4],
                "last_polled_at": row[5],
                "created_at": row[6],
                "updated_at": row[7],
                "started_at": row[8],
                "completed_at": row[9],
                "request_id": row[10],
                "provider_id": row[11],
                "strategy_id": row[12],
                "strategy_name": row[13],
            })

        return results


@app.command()
def local() -> None:
    """Show local batch request status from database."""
    async def _run() -> None:
        tasks = await _get_local_batch_status()

        if not tasks:
            console.print("[yellow]No OpenAI batch tasks found in database[/yellow]")
            return

        table = Table(title="Local OpenAI Batch Tasks")
        table.add_column("Task ID", style="cyan", no_wrap=False)
        table.add_column("Strategy", style="magenta")
        table.add_column("State", style="green")
        table.add_column("Provider Job ID", style="yellow")
        table.add_column("Created", style="blue")
        table.add_column("Completed", style="blue")
        table.add_column("Last Poll Status", style="cyan")
        table.add_column("Last Polled At", style="blue")

        for task in tasks:
            provider_job_id = task["provider_job_id"] or "[dim]not submitted[/dim]"
            poll_status = task["last_poll_status"] or "[dim]-[/dim]"

            table.add_row(
                task["task_id"][:36],
                task["strategy_name"] or task["strategy_id"][:36],
                task["lifecycle_state"],
                provider_job_id,
                _format_timestamp(task["created_at"]),
                _format_timestamp(task["completed_at"]),
                poll_status,
                _format_timestamp(task["last_polled_at"]),
            )

        console.print(table)
        console.print(f"\n[green]Total tasks: {len(tasks)}[/green]")

        # Summary by state
        from collections import Counter
        state_counts = Counter(t["lifecycle_state"] for t in tasks)
        console.print("\n[bold]Summary by state:[/bold]")
        for state, count in state_counts.most_common():
            console.print(f"  {state}: {count}")

    asyncio.run(_run())


@app.command()
def remote(limit: int = typer.Option(100, help="Maximum number of batches to retrieve")) -> None:
    """List batch jobs from OpenAI API."""
    async def _run() -> None:
        try:
            batches = await _list_openai_batches(limit)

            if not batches:
                console.print("[yellow]No batch jobs found in OpenAI account[/yellow]")
                return

            table = Table(title="OpenAI Batch Jobs (from API)")
            table.add_column("Batch ID", style="cyan", no_wrap=False)
            table.add_column("Status", style="green")
            table.add_column("Created", style="blue")
            table.add_column("Completed", style="blue")
            table.add_column("Total", style="yellow")
            table.add_column("Completed", style="green")
            table.add_column("Failed", style="red")

            for batch in batches:
                counts = batch.get("request_counts", {})
                created = batch.get("created_at", 0)
                completed_at = batch.get("completed_at", 0)

                # Convert timestamps to readable format
                created_str = "-"
                if created:
                    created_str = datetime.fromtimestamp(created, tz=UTC).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )
                completed_str = "-"
                if completed_at:
                    completed_str = datetime.fromtimestamp(
                        completed_at, tz=UTC
                    ).strftime("%Y-%m-%d %H:%M:%S")

                table.add_row(
                    batch.get("id", "")[:40],
                    batch.get("status", "unknown"),
                    created_str,
                    completed_str,
                    str(counts.get("total", 0)),
                    str(counts.get("completed", 0)),
                    str(counts.get("failed", 0)),
                )

            console.print(table)
            console.print(f"\n[green]Total batches: {len(batches)}[/green]")

            # Summary by status
            from collections import Counter
            status_counts = Counter(b.get("status") for b in batches)
            console.print("\n[bold]Summary by status:[/bold]")
            for status, count in status_counts.most_common():
                console.print(f"  {status}: {count}")

        except httpx.HTTPStatusError as exc:
            console.print(
                f"[red]HTTP Error: {exc.response.status_code} - {exc.response.text}[/red]"
            )
            raise typer.Exit(code=1) from exc
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(code=1) from exc

    asyncio.run(_run())


@app.command()
def compare() -> None:
    """Compare local database state with OpenAI API state."""
    async def _run() -> None:
        console.print("[cyan]Fetching local tasks...[/cyan]")
        local_tasks = await _get_local_batch_status()

        console.print("[cyan]Fetching remote batches...[/cyan]")
        try:
            remote_batches = await _list_openai_batches()
        except Exception as e:
            console.print(f"[red]Error fetching remote batches: {e}[/red]")
            remote_batches = []

        # Create lookup by provider_job_id
        remote_by_id = {b["id"]: b for b in remote_batches}

        console.print("\n[bold]Comparison:[/bold]\n")

        # Tasks with provider job IDs
        submitted_tasks = [t for t in local_tasks if t["provider_job_id"]]
        pending_tasks = [t for t in local_tasks if not t["provider_job_id"]]

        if submitted_tasks:
            console.print(f"[green]Tasks submitted to OpenAI: {len(submitted_tasks)}[/green]")
            for task in submitted_tasks:
                job_id = task["provider_job_id"]
                local_state = task["lifecycle_state"]
                remote_batch = remote_by_id.get(job_id)

                if remote_batch:
                    remote_status = remote_batch.get("status", "unknown")
                    counts = remote_batch.get("request_counts", {})
                    console.print(f"  • {job_id[:40]}")
                    console.print(f"    Local: {local_state} | Remote: {remote_status}")
                    console.print(f"    Counts: {counts}")
                else:
                    console.print(f"  • {job_id[:40]}")
                    console.print(f"    Local: {local_state} | Remote: [red]NOT FOUND[/red]")
        else:
            console.print("[yellow]No tasks have been submitted to OpenAI yet[/yellow]")

        if pending_tasks:
            pending_count = len(pending_tasks)
            console.print(f"\n[yellow]Tasks pending submission: {pending_count}[/yellow]")
            for task in pending_tasks[:10]:  # Show first 10
                strategy_label = task["strategy_name"] or task["strategy_id"][:36]
                console.print(
                    f"  • {task['task_id'][:36]} - {strategy_label} ({task['lifecycle_state']})"
                )
            if pending_count > 10:
                console.print(f"  ... and {pending_count - 10} more")

        # Remote batches not in local DB
        local_job_ids = {t["provider_job_id"] for t in submitted_tasks}
        orphaned_batches = [b for b in remote_batches if b["id"] not in local_job_ids]

        if orphaned_batches:
            orphan_count = len(orphaned_batches)
            console.print(
                f"\n[magenta]Remote batches not tracked locally: {orphan_count}[/magenta]"
            )
            for batch in orphaned_batches[:10]:  # Show first 10
                status_label = batch.get("status", "unknown")
                console.print(f"  • {batch['id'][:40]} - {status_label}")
            if orphan_count > 10:
                console.print(f"  ... and {orphan_count - 10} more")

    asyncio.run(_run())


@app.command()
def details(
    batch_id: str = typer.Argument(..., help="OpenAI batch job ID"),
) -> None:
    """Get detailed information about a specific batch job."""
    async def _run() -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            console.print("[red]Error: OPENAI_API_KEY not found in environment[/red]")
            raise typer.Exit(code=1)

        endpoint = os.getenv("OPENAI_API_BASE", "https://api.openai.com")
        endpoint = endpoint.rstrip("/")

        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(
                base_url=endpoint,
                timeout=30.0,
                headers=headers,
            ) as client:
                response = await client.get(f"/v1/batches/{batch_id}")
                response.raise_for_status()
                batch = response.json()

            console.print(json.dumps(batch, indent=2))

        except httpx.HTTPStatusError as exc:
            console.print(
                f"[red]HTTP Error: {exc.response.status_code} - {exc.response.text}[/red]"
            )
            raise typer.Exit(code=1) from exc
        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(code=1) from exc

    asyncio.run(_run())


if __name__ == "__main__":
    app()
