"""Shared CLI dependency helpers."""

from __future__ import annotations

from functools import lru_cache

from folios_v2.config import AppSettings
from folios_v2.container import ServiceContainer, build_container


@lru_cache(maxsize=1)
def get_container() -> ServiceContainer:
    """Return a cached service container for CLI commands."""

    settings = AppSettings.from_env()
    return build_container(settings)


def reset_container() -> None:
    """Clear the cached container (useful for tests)."""

    get_container.cache_clear()
