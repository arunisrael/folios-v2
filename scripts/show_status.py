#!/usr/bin/env python3
"""Show status of pending and completed requests."""

import asyncio
from pathlib import Path

from dotenv import load_dotenv

# Load .env file
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

from folios_v2.cli.deps import get_container


async def main() -> None:
    container = get_container()

    async with container.unit_of_work_factory() as uow:
        # Get pending requests
        pending = await uow.request_repository.list_pending(limit=100)

        print(f"Pending Requests: {len(pending)}")
        for req in pending[:10]:
            print(f"  - {req.id}: {req.provider_id.value} ({req.mode.value})")

        if len(pending) > 10:
            print(f"  ... and {len(pending) - 10} more")


if __name__ == "__main__":
    asyncio.run(main())
