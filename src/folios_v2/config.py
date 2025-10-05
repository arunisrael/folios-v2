"""Lightweight application configuration loader."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AppSettings:
    """Immutable configuration sourced from environment variables."""

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///folios_v2.db"
    artifacts_root: Path = Path("artifacts")
    timezone: str = "UTC"

    @classmethod
    def from_env(cls) -> AppSettings:
        return cls(
            environment=os.getenv("FOLIOS_ENV", cls.environment),
            database_url=os.getenv("FOLIOS_DATABASE_URL", cls.database_url),
            artifacts_root=Path(os.getenv("FOLIOS_ARTIFACTS_ROOT", str(cls.artifacts_root))),
            timezone=os.getenv("FOLIOS_TIMEZONE", cls.timezone),
        )


__all__ = ["AppSettings"]
