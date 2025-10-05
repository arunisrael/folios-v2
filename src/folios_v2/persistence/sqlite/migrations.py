"""SQLite migrations for Folios v2."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .models import Base

Migration = Callable[[AsyncEngine], Awaitable[None]]


async def _initial_migration(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS folios_schema_migrations (version INTEGER PRIMARY KEY)"
            )
        )
        result = await conn.execute(text("SELECT MAX(version) FROM folios_schema_migrations"))
        current = result.scalar()
        if current is None:
            await conn.execute(text("INSERT INTO folios_schema_migrations (version) VALUES (1)"))


async def apply_migrations(engine: AsyncEngine) -> None:
    await _initial_migration(engine)


__all__ = ["apply_migrations"]
