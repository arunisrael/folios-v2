#!/usr/bin/env python3
"""Check portfolio status after applying recommendations."""

import asyncio
from uuid import UUID

from folios_v2.cli.deps import get_container
from folios_v2.domain.enums import ProviderId
from folios_v2.domain.types import StrategyId


async def main():
    """Check all portfolios."""
    container = get_container()

    # Strategy IDs from our execution
    strategy_ids = [
        "68b86a90-3ac3-4253-985b-0dde7f493e11",  # Cigar-Butt Deep Value
        "d75d1377-1721-4f1b-852c-f54bb495847a",  # Benjamin Graham Strategy
        "80d44909-097d-41c3-88ae-cca446a632a1",  # Jacob Little Strategy
        "9bd5e8cc-33c1-4c82-ac2d-eac5c7991337",  # Guy Spier Strategy
        "63056a65-1cca-44b8-9781-c557722a4a51",  # Global Macro Investing
        "d605360c-aa90-4db7-b588-4ec65dc660c6",  # Daniel Loeb Strategy
        "8b5ab2d0-d664-4e47-b437-ed25fed7cbf5",  # Christopher Browne Strategy
        "42ccd1a7-e47e-4b47-aab2-9417ede4f0b3",  # Charles Brandes Strategy
        "9119eab4-3c5d-4b5d-bd0f-6e08aa302671",  # Nicolas Darvas Strategy
        "e04d2c5d-0811-4441-bd0c-2807446dad1d",  # Bill Ackman Strategy
    ]

    print(f"{'='*80}")
    print("PORTFOLIO STATUS CHECK")
    print(f"{'='*80}")

    total_cash = 0
    total_equity = 0
    total_positions = 0

    async with container.unit_of_work_factory() as uow:
        for strategy_id_str in strategy_ids:
            strategy_id = StrategyId(UUID(strategy_id_str))
            strategy = await uow.strategy_repository.get(strategy_id)

            if not strategy:
                print(f"\n⚠️  Strategy {strategy_id_str[:8]}... not found")
                continue

            # Get portfolio account
            account = await uow.portfolio_repository.get(strategy_id, ProviderId.ANTHROPIC)

            if account:
                total_value = account.cash_balance + account.equity_value
                total_cash += account.cash_balance
                total_equity += account.equity_value

                print(f"\n✓ {strategy.name}")
                print(f"  Cash: ${account.cash_balance:,.2f}")
                print(f"  Equity: ${account.equity_value:,.2f}")
                print(f"  Total: ${total_value:,.2f}")

                # Count positions for this strategy
                # Note: We'd need a method to get positions by strategy
                # For now, just show the account status
            else:
                print(f"\n⚠️  {strategy.name}")
                print("  No portfolio account found")

    print(f"\n{'='*80}")
    print("TOTALS")
    print(f"{'='*80}")
    print(f"Total Cash: ${total_cash:,.2f}")
    print(f"Total Equity: ${total_equity:,.2f}")
    print(f"Total Portfolio Value: ${total_cash + total_equity:,.2f}")
    print(f"{'='*80}")


if __name__ == "__main__":
    asyncio.run(main())
