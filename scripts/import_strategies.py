"""Import legacy Folios strategies into the v2 SQLite store."""

from __future__ import annotations

# ruff: noqa: B008
import asyncio
import hashlib
import json
import sqlite3
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, time
from pathlib import Path
from typing import Any

import typer

from folios_v2.domain import (
    ProviderPreference,
    RiskControls,
    Strategy,
    StrategyMetadata,
    StrategySchedule,
)
from folios_v2.domain.enums import ExecutionMode, ProviderId, StrategyStatus
from folios_v2.domain.types import StrategyId
from folios_v2.persistence.sqlite import create_sqlite_unit_of_work_factory
from folios_v2.utils import ensure_utc

DEFAULT_SOURCE = Path("../folios-py/development.db")
DEFAULT_TARGET = "sqlite+aiosqlite:///folios_v2.db"
LEGACY_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "folios.v2.legacy.strategies")

app = typer.Typer(help="Migrate folios-py strategies into the Folios v2 database")


def _clean_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _load_legacy_rows(source: Path, limit: int | None) -> list[dict[str, Any]]:
    query = (
        "select id, name, prompt, tickers, risk_controls, metadata, schedule, "
        "options_enabled, short_enabled, is_active, created_at, updated_at "
        "from strategies order by created_at asc"
    )

    with sqlite3.connect(source) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.execute(query + (" limit ?" if limit else ""), (limit,) if limit else ())
        return [dict(row) for row in cursor.fetchall()]


def _parse_risk_controls(raw: str | None) -> RiskControls | None:
    if not raw:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None

    numeric_fields = (
        "max_position_size",
        "max_exposure",
        "stop_loss",
        "max_leverage",
        "max_short_exposure",
        "max_single_name_short",
    )
    rc_kwargs: dict[str, Any] = {}
    for field in numeric_fields:
        value = data.get(field)
        if value is not None:
            rc_kwargs[field] = float(value)

    if "max_position_size" not in rc_kwargs:
        return None

    rc_kwargs["borrow_available"] = data.get("borrow_available")
    return RiskControls(**rc_kwargs)


def _resolve_weekday(token: str, legacy_id: str) -> int:
    if token.isdigit():
        value = int(token)
        if value in (0, 7):
            return 1
        if value == 6:
            return 5
        if 1 <= value <= 5:
            return value
    digest = hashlib.sha256(legacy_id.encode("utf-8")).digest()
    # Falling back to a stable hash keeps weekdays deterministic without clustering.
    return (digest[0] % 5) + 1


def _parse_schedule(expr: str, legacy_id: str) -> tuple[int, time | None]:
    parts = expr.split()
    research_time: time | None = None
    if len(parts) >= 3 and parts[2].isdigit():
        research_time = time(hour=int(parts[2]), tzinfo=UTC)

    weekday_token = parts[5] if len(parts) >= 6 else "*"
    weekday = _resolve_weekday(weekday_token, legacy_id)
    return weekday, research_time


def _parse_metadata(row: dict[str, Any], legacy_id: str) -> StrategyMetadata | None:
    raw = row.get("metadata")
    if not raw:
        return None
    data = json.loads(raw)
    if not isinstance(data, dict):
        return None

    description = _clean_text(data.get("description")) or _clean_text(row.get("prompt"))
    if not description:
        description = row["name"].strip()

    extras: list[str] = [f"Legacy ID: {legacy_id}"]
    rationale = _clean_text(data.get("rationale"))
    if rationale:
        extras.append(f"Rationale: {rationale}")
    market = _clean_text(data.get("market_conditions"))
    if market:
        extras.append(f"Market conditions: {market}")

    flags: list[str] = []
    if bool(row.get("options_enabled")):
        flags.append("options-enabled")
    if bool(row.get("short_enabled")):
        flags.append("short-enabled")
    if flags:
        extras.append("Legacy flags: " + ", ".join(flags))

    if extras:
        description = description + "\n\n" + "\n".join(extras)

    theme = _clean_text(data.get("category"))
    risk_level = _clean_text(data.get("risk_level"))
    time_horizon = _clean_text(data.get("time_horizon"))

    key_metrics_raw = data.get("key_metrics") or []
    key_metrics = tuple(_clean_text(item) for item in key_metrics_raw if _clean_text(item))
    key_metrics = key_metrics or None

    key_signals_raw = data.get("key_signals") or []
    key_signals = tuple(_clean_text(item) for item in key_signals_raw if _clean_text(item))
    key_signals = key_signals or None

    return StrategyMetadata(
        description=description,
        theme=theme,
        risk_level=risk_level,
        time_horizon=time_horizon,
        key_metrics=key_metrics,
        key_signals=key_signals,
    )


def _transform_row(row: dict[str, Any]) -> tuple[Strategy, StrategySchedule]:
    legacy_id = row["id"]
    strategy_id = StrategyId(uuid.uuid5(LEGACY_NAMESPACE, legacy_id))

    tickers_raw = json.loads(row["tickers"]) if row.get("tickers") else []
    tickers = tuple(str(ticker).strip() for ticker in tickers_raw if str(ticker).strip())

    risk_controls = _parse_risk_controls(row.get("risk_controls"))
    metadata = _parse_metadata(row, legacy_id)
    weekday, research_time = _parse_schedule((row.get("schedule") or "").strip(), legacy_id)

    created_at = ensure_utc(datetime.fromisoformat(row["created_at"]))
    updated_at = ensure_utc(datetime.fromisoformat(row["updated_at"]))

    status = StrategyStatus.ACTIVE if bool(row.get("is_active")) else StrategyStatus.DRAFT
    preferred = ProviderPreference(
        provider_id=ProviderId.OPENAI,
        execution_modes=(ExecutionMode.BATCH, ExecutionMode.CLI),
        rank=1,
    )

    strategy = Strategy(
        id=strategy_id,
        name=row["name"].strip(),
        prompt=row["prompt"],
        tickers=tickers,
        status=status,
        risk_controls=risk_controls,
        metadata=metadata,
        preferred_providers=(preferred,),
        active_modes=(ExecutionMode.BATCH, ExecutionMode.CLI),
        research_day=weekday,
        research_time_utc=research_time,
        runtime_weight=1.0,
        created_at=created_at,
        updated_at=updated_at,
    )

    schedule = StrategySchedule(
        strategy_id=strategy.id,
        weekday=weekday,
        next_research_at=None,
        last_research_at=None,
    )

    return strategy, schedule


async def _persist(
    strategies: Sequence[Strategy],
    schedules: Sequence[StrategySchedule],
    database_url: str,
    batch_size: int,
) -> None:
    factory = create_sqlite_unit_of_work_factory(database_url)
    async with factory() as uow:
        for index, (strategy, schedule) in enumerate(
            zip(strategies, schedules, strict=False), start=1
        ):
            await uow.strategy_repository.upsert(strategy)
            await uow.schedule_repository.upsert(schedule)
            if index % batch_size == 0:
                await uow.commit()
        await uow.commit()


@app.command()
def run(
    source: Path = typer.Option(
        DEFAULT_SOURCE,
        help="Path to folios-py SQLite database",
    ),
    target: str = typer.Option(
        DEFAULT_TARGET,
        help="Database URL for Folios v2",
    ),
    limit: int | None = typer.Option(
        None,
        min=1,
        help="Optional limit for testing",
    ),
    batch_size: int = typer.Option(
        10,
        min=1,
        help="Number of records to commit per batch",
    ),
    preview: bool = typer.Option(
        False,
        help="Preview transformed strategies without writing",
    ),
    mapping_output: Path | None = typer.Option(
        None,
        help="Optional path to write legacy-to-v2 strategy ID mapping in JSON",
    ),
) -> None:
    """Import strategies from folios-py into the Folios v2 database."""

    if not source.exists():
        typer.echo(f"Source database not found: {source}")
        raise typer.Exit(code=1)

    rows = _load_legacy_rows(source, limit)
    if not rows:
        typer.echo("No strategies found in the legacy database")
        raise typer.Exit(code=0)

    strategies: list[Strategy] = []
    schedules: list[StrategySchedule] = []
    mapping: list[dict[str, str]] = []

    for row in rows:
        strategy, schedule = _transform_row(row)
        strategies.append(strategy)
        schedules.append(schedule)
        mapping.append({"legacy_id": row["id"], "strategy_id": str(strategy.id)})

    if mapping_output is not None:
        mapping_output.parent.mkdir(parents=True, exist_ok=True)
        mapping_output.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
        typer.echo(f"Wrote legacy mapping to {mapping_output}")

    if preview:
        preview_payload = [
            {
                "legacy_id": entry["legacy_id"],
                "strategy_id": entry["strategy_id"],
                "name": strategy.name,
                "status": strategy.status.value,
                "research_day": strategy.research_day,
                "research_time_utc": strategy.research_time_utc.isoformat()
                if strategy.research_time_utc
                else None,
                "tickers": strategy.tickers,
            }
            for entry, strategy in zip(mapping, strategies, strict=False)
        ]
        typer.echo(json.dumps(preview_payload, indent=2))
        typer.echo("Preview complete — no changes applied")
        raise typer.Exit(code=0)

    asyncio.run(_persist(strategies, schedules, target, batch_size))
    typer.echo(f"Imported {len(strategies)} strategies into {target}")


if __name__ == "__main__":  # pragma: no cover
    app()
