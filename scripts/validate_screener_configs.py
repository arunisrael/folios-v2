#!/usr/bin/env python3
"""Validate screener configurations by testing them against FMP API."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from dotenv import load_dotenv

from folios_v2.screeners.providers.fmp import FMPScreener


async def test_screener_config(strategy_name: str, config: dict) -> dict:
    """Test a screener configuration."""
    screener = FMPScreener()

    try:
        result = await screener.screen(
            filters=config["filters"],
            limit=config["limit"],
        )
        return {
            "success": True,
            "count": len(result.symbols),
            "sample_symbols": list(result.symbols[:5]),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }


async def main() -> None:
    """Test sample screener configurations."""
    load_dotenv()

    # Load mapping
    mapping_path = Path(__file__).parent.parent / "data" / "strategy_screener_mapping.json"
    data = json.loads(mapping_path.read_text())

    # Select diverse sample strategies
    test_strategies = [
        "David Dreman Strategy",  # Quality (was value in original plan)
        "Walter Schloss Strategy",  # Deep value
        "Cathie Wood Strategy",  # Growth
        "Geraldine Weiss Strategy",  # Dividend
        "William O'Neil Strategy",  # Momentum
        "Value",  # Generic value
    ]

    print("Validating screener configurations...\n")

    for item in data:
        if item["name"] in test_strategies:
            name = item["name"]
            category = item["category"]
            config = item["recommended_screener"]

            print(f"{name} ({category})")
            print(f"  Filters: {config['filters']}")
            print(f"  Limit: {config['limit']}")

            result = await test_screener_config(name, config)

            if result["success"]:
                print(f"  ✓ Returned {result['count']} symbols")
                if result["sample_symbols"]:
                    print(f"  Sample: {', '.join(result['sample_symbols'])}")
            else:
                print(f"  ✗ Error: {result['error']}")

            print()

    print("\nValidation complete!")


if __name__ == "__main__":
    asyncio.run(main())
