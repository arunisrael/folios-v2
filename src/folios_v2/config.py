"""Lightweight application configuration loader."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no"}


@dataclass(frozen=True)
class AppSettings:
    """Immutable configuration sourced from environment variables."""

    environment: str = "development"
    database_url: str = "sqlite+aiosqlite:///folios_v2.db"
    artifacts_root: Path = Path("artifacts")
    timezone: str = "UTC"
    finnhub_api_key: str | None = None
    fmp_api_key: str | None = None
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    anthropic_api_key: str | None = None
    enable_local_batch_fallback: bool = True
    openai_batch_model: str = "gpt-4o-mini"
    openai_api_base: str = "https://api.openai.com"
    openai_completion_window: str = "24h"
    openai_batch_system_message: str = (
        "You are a research analyst returning JSON that conforms to the investment_analysis_v1 schema. "
        "Respond with valid JSON only."
    )
    gemini_batch_model: str = "gemini-2.5-pro"

    @classmethod
    def from_env(cls) -> AppSettings:
        return cls(
            environment=os.getenv("FOLIOS_ENV", cls.environment),
            database_url=os.getenv("FOLIOS_DATABASE_URL", cls.database_url),
            artifacts_root=Path(os.getenv("FOLIOS_ARTIFACTS_ROOT", str(cls.artifacts_root))),
            timezone=os.getenv("FOLIOS_TIMEZONE", cls.timezone),
            finnhub_api_key=os.getenv("FINNHUB_API_KEY") or None,
            fmp_api_key=os.getenv("FMP_API_KEY") or None,
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            gemini_api_key=os.getenv("GEMINI_API_KEY") or None,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
            enable_local_batch_fallback=_env_bool("FOLIOS_LOCAL_BATCH_FALLBACK", True),
            openai_batch_model=os.getenv("OPENAI_BATCH_MODEL", cls.openai_batch_model),
            openai_api_base=os.getenv("OPENAI_API_BASE", cls.openai_api_base),
            openai_completion_window=os.getenv(
                "OPENAI_COMPLETION_WINDOW", cls.openai_completion_window
            ),
            openai_batch_system_message=os.getenv(
                "OPENAI_BATCH_SYSTEM_MESSAGE", cls.openai_batch_system_message
            ),
            gemini_batch_model=os.getenv("GEMINI_BATCH_MODEL", cls.gemini_batch_model),
        )


__all__ = ["AppSettings"]
