"""Check status of Gemini batch requests."""

from __future__ import annotations

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import typer
from dotenv import load_dotenv
from google import genai
from rich.console import Console
from rich.table import Table
from sqlalchemy import text

from folios_v2.cli.deps import get_container

app = typer.Typer(help="Check Gemini batch request status")
console = Console()


def _format_timestamp(value: object) -> str:
    if not value:
        return "[dim]-[/dim]"
    if isinstance(value, str):
        return value[:19]
    return str(value)


_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


async def _get_local_batch_status() -> list[dict]:
    """Get Gemini batch status from local database."""
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
            WHERE r.mode = 'batch' AND r.provider_id = 'gemini'
            ORDER BY et.created_at DESC
        """

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


def _get_gemini_client() -> genai.Client:
    """Create a Gemini API client."""
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        console.print("[red]Error: GEMINI_API_KEY or GOOGLE_API_KEY not found in environment[/red]")
        raise typer.Exit(code=1)

    # Use long timeout for batch operations (10 minutes in milliseconds)
    return genai.Client(api_key=api_key, http_options={"timeout": 600000})


async def _get_batch_job(job_id: str) -> dict:
    """Get batch job details from Gemini API."""
    def _fetch() -> dict:
        client = _get_gemini_client()
        job = client.batches.get(name=job_id)

        # Convert job object to dict
        state = getattr(getattr(job, "state", None), "name", "UNKNOWN")
        counts = getattr(job, "batch_stats", None)

        return {
            "name": getattr(job, "name", job_id),
            "state": state,
            "total_requests": getattr(counts, "total_requests", 0) if counts else 0,
            "completed_requests": getattr(counts, "completed_requests", 0) if counts else 0,
            "failed_requests": getattr(counts, "failed_requests", 0) if counts else 0,
            "create_time": getattr(job, "create_time", None),
        }

    return await asyncio.to_thread(_fetch)


@app.command()
def local() -> None:
    """Show local Gemini batch request status from database."""
    async def _run() -> None:
        tasks = await _get_local_batch_status()

        if not tasks:
            console.print("[yellow]No Gemini batch tasks found in database[/yellow]")
            return

        table = Table(title="Local Gemini Batch Tasks")
        table.add_column("Task ID", style="cyan", no_wrap=False)
        table.add_column("Strategy", style="magenta")
        table.add_column("State", style="green")
        table.add_column("Provider Job ID", style="yellow", no_wrap=False)
        table.add_column("Created", style="blue")
        table.add_column("Started", style="blue")
        table.add_column("Last Poll Status", style="cyan")
        table.add_column("Last Polled At", style="blue")

        for task in tasks:
            provider_job_id = task["provider_job_id"] or "[dim]not submitted[/dim]"
            poll_status = task["last_poll_status"] or "[dim]-[/dim]"
            provider_display = (
                provider_job_id[:50]
                if provider_job_id != "[dim]not submitted[/dim]"
                else provider_job_id
            )

            table.add_row(
                task["task_id"][:36],
                task["strategy_name"] or task["strategy_id"][:36],
                task["lifecycle_state"],
                provider_display,
                _format_timestamp(task["created_at"]),
                _format_timestamp(task["started_at"]),
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
def status(
    job_id_arg: str = typer.Argument(None, help="Specific Gemini batch job ID to check"),
) -> None:
    """Check status of Gemini batch jobs (all or specific job)."""
    async def _run() -> None:
        if job_id_arg:
            # Check specific job
            try:
                console.print(f"[cyan]Fetching status for job: {job_id_arg}[/cyan]\n")
                job_info = await _get_batch_job(job_id_arg)

                console.print(f"[bold]Job ID:[/bold] {job_info['name']}")
                console.print(f"[bold]State:[/bold] {job_info['state']}")
                console.print(f"[bold]Total Requests:[/bold] {job_info['total_requests']}")
                console.print(f"[bold]Completed:[/bold] {job_info['completed_requests']}")
                console.print(f"[bold]Failed:[/bold] {job_info['failed_requests']}")

                if job_info.get('create_time'):
                    create_time = job_info['create_time']
                    if hasattr(create_time, 'timestamp'):
                        ts = create_time.timestamp()
                        dt = datetime.fromtimestamp(ts, tz=UTC)
                        created_label = dt.strftime("%Y-%m-%d %H:%M:%S UTC")
                        console.print(f"[bold]Created:[/bold] {created_label}")

            except Exception as exc:
                console.print(f"[red]Error: {exc}[/red]")
                raise typer.Exit(code=1) from exc
        else:
            # Check all jobs from local DB
            tasks = await _get_local_batch_status()
            submitted_tasks = [t for t in tasks if t["provider_job_id"]]

            if not submitted_tasks:
                console.print("[yellow]No submitted Gemini batch jobs found[/yellow]")
                return

            console.print(
                f"[cyan]Checking status for {len(submitted_tasks)} Gemini batch jobs...[/cyan]\n"
            )

            table = Table(title="Gemini Batch Jobs Status")
            table.add_column("Local ID", style="cyan", no_wrap=False)
            table.add_column("Provider Job ID", style="yellow", no_wrap=False)
            table.add_column("Local State", style="green")
            table.add_column("Remote State", style="magenta")
            table.add_column("Total", style="blue")
            table.add_column("Done", style="green")
            table.add_column("Failed", style="red")

            for task in submitted_tasks:
                job_id = task["provider_job_id"]
                local_state = task["lifecycle_state"]

                try:
                    job_info = await _get_batch_job(job_id)
                    remote_state = job_info["state"]
                    total = job_info["total_requests"]
                    completed = job_info["completed_requests"]
                    failed = job_info["failed_requests"]

                    table.add_row(
                        task["task_id"][:24],
                        job_id[:40] if len(job_id) > 40 else job_id,
                        local_state,
                        remote_state,
                        str(total),
                        str(completed),
                        str(failed),
                    )
                except Exception as e:
                    table.add_row(
                        task["task_id"][:24],
                        job_id[:40] if len(job_id) > 40 else job_id,
                        local_state,
                        f"[red]ERROR: {str(e)[:20]}[/red]",
                        "-",
                        "-",
                        "-",
                    )

            console.print(table)

    asyncio.run(_run())


@app.command()
def details(
    job_id: str = typer.Argument(..., help="Gemini batch job ID"),
) -> None:
    """Get detailed information about a specific batch job."""
    async def _run() -> None:
        try:
            def _fetch() -> dict:
                client = _get_gemini_client()
                job = client.batches.get(name=job_id)

                # Try to serialize the job object
                job_dict = {}
                for attr in dir(job):
                    if attr.startswith("_"):
                        continue
                    try:
                        value = getattr(job, attr)
                    except AttributeError:
                        continue
                    if callable(value):
                        continue
                    if hasattr(value, "__dict__"):
                        job_dict[attr] = str(value)
                    else:
                        job_dict[attr] = value

                return job_dict

            job_dict = await asyncio.to_thread(_fetch)
            console.print(json.dumps(job_dict, indent=2, default=str))

        except Exception as exc:
            console.print(f"[red]Error: {exc}[/red]")
            raise typer.Exit(code=1) from exc

    asyncio.run(_run())


if __name__ == "__main__":
    app()
