#!/usr/bin/env python3
"""Analyze all strategies and recommend screener configurations."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

# Strategy categories and their screener templates
SCREENER_TEMPLATES = {
    "value": {
        "market_cap_min": 500_000_000,
        "price_min": 5,
        "avg_vol_min": 100_000,
        "pe_max": 20,
    },
    "deep_value": {
        "market_cap_min": 300_000_000,
        "price_min": 3,
        "avg_vol_min": 50_000,
        "pe_max": 15,
    },
    "growth": {
        "market_cap_min": 10_000_000_000,
        "price_min": 10,
        "avg_vol_min": 500_000,
    },
    "dividend": {
        "market_cap_min": 1_000_000_000,
        "price_min": 10,
        "avg_vol_min": 200_000,
        "pe_max": 25,
    },
    "momentum": {
        "market_cap_min": 1_000_000_000,
        "price_min": 5,
        "avg_vol_min": 1_000_000,
    },
    "large_cap": {
        "market_cap_min": 10_000_000_000,
        "price_min": 10,
        "avg_vol_min": 500_000,
    },
    "mid_cap": {
        "market_cap_min": 2_000_000_000,
        "market_cap_max": 10_000_000_000,
        "price_min": 5,
        "avg_vol_min": 200_000,
    },
    "small_cap": {
        "market_cap_min": 300_000_000,
        "market_cap_max": 2_000_000_000,
        "price_min": 3,
        "avg_vol_min": 50_000,
    },
    "broad_market": {
        "market_cap_min": 500_000_000,
        "price_min": 5,
        "avg_vol_min": 100_000,
    },
    "quality": {
        "market_cap_min": 2_000_000_000,
        "price_min": 10,
        "avg_vol_min": 300_000,
    },
}

# Optimal limits by category
LIMIT_BY_CATEGORY = {
    "value": 300,
    "deep_value": 300,
    "growth": 100,
    "dividend": 200,
    "momentum": 150,
    "large_cap": 100,
    "mid_cap": 200,
    "small_cap": 250,
    "broad_market": 200,
    "quality": 150,
}


def analyze_strategy(name: str, prompt: str, theme: str | None) -> dict[str, Any]:
    """Analyze a strategy and recommend screener configuration."""
    name_lower = name.lower()
    prompt_lower = (prompt or "").lower()
    theme_lower = (theme or "").lower()
    combined = f"{name_lower} {prompt_lower} {theme_lower}"

    # Determine category and customizations
    category = "broad_market"  # default
    filters = {}
    limit = 200
    sector = None

    # Priority order matters - check most specific first

    # Deep value strategies (before general value)
    if any(
        x in combined
        for x in ["deep value", "cigar-butt", "cigar butt", "net-net", "liquidation", "schloss"]
    ):
        category = "deep_value"

    # Growth strategies (check before value to catch growth investors)
    elif any(
        x in combined
        for x in ["cathie wood", "ark invest", "growth at reasonable", "garp", "peter lynch"]
    ):
        category = "growth"

    # Momentum strategies
    elif any(x in combined for x in ["momentum", "canslim", "o'neil", "oneil", "trend following"]):
        category = "momentum"

    # Dividend strategies
    elif any(
        x in combined for x in ["dividend", "income", "dogs of the dow", "aristocrat", "yield"]
    ):
        category = "dividend"

    # Quality/Moat (before general value)
    elif any(
        x in combined
        for x in [
            "quality",
            "moat",
            "sustainable competitive advantage",
            "buffett",
            "munger",
            "blue chip",
        ]
    ):
        category = "quality"

    # Large cap (check before general value)
    elif any(
        x in combined
        for x in ["large cap", "large-cap", "mega cap", "mega-cap", "s&p 500", "dow jones"]
    ):
        category = "large_cap"

    # Mid cap
    elif any(x in combined for x in ["mid cap", "mid-cap"]):
        category = "mid_cap"

    # Small cap
    elif any(
        x in combined
        for x in ["small cap", "micro cap", "small-cap", "micro-cap", "microcap", "smallcap"]
    ):
        category = "small_cap"

    # Value strategies (broader catch-all)
    elif any(
        x in combined
        for x in [
            "value",
            "graham",
            "dreman",
            "klarman",
            "activist",
            "contrarian",
            "margin of safety",
            "p/e ratio",
            "p/b ratio",
            "undervalued",
        ]
    ):
        category = "value"

    # Risk Parity / Asset Allocation
    elif any(
        x in combined for x in ["risk parity", "all weather", "asset allocation", "diversified"]
    ):
        category = "broad_market"

    # Get base template
    filters = dict(SCREENER_TEMPLATES[category])
    limit = LIMIT_BY_CATEGORY[category]

    # Sector-specific customizations
    if "technology" in combined or "tech" in combined:
        sector = "Technology"
    elif "healthcare" in combined or "biotech" in combined:
        sector = "Healthcare"
    elif "financ" in combined:
        sector = "Financial Services"
    elif "energy" in combined:
        sector = "Energy"
    elif "consumer" in combined:
        if "staples" in combined:
            sector = "Consumer Defensive"
        elif "discretionary" in combined or "cyclical" in combined:
            sector = "Consumer Cyclical"
    elif "industrial" in combined:
        sector = "Industrials"
    elif "real estate" in combined or "reit" in combined:
        sector = "Real Estate"

    if sector:
        filters["sector"] = sector

    # Exchange-specific
    if "nasdaq" in combined:
        filters["exchange"] = "NASDAQ"

    return {
        "category": category,
        "filters": filters,
        "limit": limit,
        "reasoning": f"Category: {category}, Sector: {sector or 'All'}",
    }


def main() -> None:
    """Main analysis function."""
    db_path = Path(__file__).parent.parent / "folios_v2.db"
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            name,
            json_extract(payload, '$.prompt') as prompt,
            json_extract(payload, '$.metadata.theme') as theme,
            json_extract(payload, '$.screener') as current_screener
        FROM strategies
        ORDER BY name
    """)

    results = []
    category_counts = {}

    for row in cursor.fetchall():
        strategy_id, name, prompt, theme, current_screener = row

        analysis = analyze_strategy(name, prompt, theme)
        category = analysis["category"]
        category_counts[category] = category_counts.get(category, 0) + 1

        results.append({
            "id": strategy_id,
            "name": name,
            "category": category,
            "recommended_screener": {
                "provider": "fmp",
                "filters": analysis["filters"],
                "limit": analysis["limit"],
                "enabled": True,
            },
            "current_screener": json.loads(current_screener) if current_screener else None,
            "reasoning": analysis["reasoning"],
        })

    conn.close()

    # Write results
    output_path = Path(__file__).parent.parent / "data" / "strategy_screener_mapping.json"
    output_path.parent.mkdir(exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(results, f, indent=2)

    # Print summary
    print(f"✓ Analyzed {len(results)} strategies")
    print(f"✓ Saved to {output_path}")
    print("\nCategory distribution:")
    for category, count in sorted(category_counts.items()):
        print(f"  {category}: {count}")

    # Print sample recommendations
    print("\nSample recommendations:")
    for result in results[:5]:
        print(f"\n{result['name']}:")
        print(f"  Category: {result['category']}")
        print(f"  Filters: {result['recommended_screener']['filters']}")
        print(f"  Limit: {result['recommended_screener']['limit']}")


if __name__ == "__main__":
    main()
