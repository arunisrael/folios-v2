from __future__ import annotations

import asyncio
from pathlib import Path

from folios_v2.config import AppSettings
from folios_v2.container import build_container
from folios_v2.domain import ProviderId


def test_build_container_registers_providers(tmp_path: Path) -> None:
    db_url = f"sqlite+aiosqlite:///{tmp_path/'container.db'}"
    settings = AppSettings(
        environment="test",
        database_url=db_url,
        artifacts_root=tmp_path / "artifacts",
        timezone="UTC",
    )

    container = build_container(settings)

    assert (tmp_path / "artifacts").exists()
    providers = {plugin.provider_id for plugin in container.provider_registry.list_plugins()}
    assert providers == {ProviderId.OPENAI, ProviderId.GEMINI, ProviderId.ANTHROPIC}

    async def _round_trip() -> int:
        async with container.unit_of_work_factory() as uow:
            strategies = await uow.strategy_repository.list_active()
            await uow.commit()
        return len(strategies)

    assert asyncio.run(_round_trip()) == 0
