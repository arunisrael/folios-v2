#!/usr/bin/env python3
"""Test FMP API screener limit."""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv

from folios_v2.screeners.providers.fmp import FMPScreener


async def test_limit(limit: int) -> int:
    """Test screener with a specific limit."""
    load_dotenv()
    screener = FMPScreener()

    print(f"\nTesting limit={limit}...")
    try:
        result = await screener.screen(
            filters={
                "market_cap_min": 1_000_000_000,
                "price_min": 5,
            },
            limit=limit,
        )
        count = len(result.symbols)
        print(f"  ✓ Returned {count} symbols")
        return count
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return -1


async def main() -> None:
    """Test various limits."""
    print("Testing FMP API screener limits...")

    limits_to_test = [50, 100, 200, 300, 500, 1000]

    for limit in limits_to_test:
        count = await test_limit(limit)
        if count == -1:
            break
        if count < limit:
            print(f"\n  ⚠️  API returned fewer results ({count}) than requested ({limit})")
            print(f"  → Effective maximum appears to be around {count}")
            break

    print("\nRecommendations:")
    print("  - Deep value/Value strategies: limit=300")
    print("  - Dividend strategies: limit=200")
    print("  - Quality/Mid-cap strategies: limit=150")
    print("  - Growth/Large-cap strategies: limit=100")
    print("  - Momentum strategies: limit=150")


if __name__ == "__main__":
    asyncio.run(main())
