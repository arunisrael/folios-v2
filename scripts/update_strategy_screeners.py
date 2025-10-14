#!/usr/bin/env python3
"""Update all strategy screener configurations with tailored FMP criteria."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path


def load_screener_mapping() -> dict[str, dict]:
    """Load the strategy-to-screener mapping from JSON file."""
    mapping_path = Path(__file__).parent.parent / "data" / "strategy_screener_mapping.json"
    with open(mapping_path) as f:
        data = json.load(f)

    # Convert list to name-keyed dictionary
    return {item["name"]: item["recommended_screener"] for item in data}


def update_screeners(db_path: str, dry_run: bool = True) -> None:
    """Update screener configs for all strategies."""
    screener_mapping = load_screener_mapping()

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all strategies
    cursor.execute("SELECT id, name, payload FROM strategies")
    updated_count = 0
    skipped_count = 0

    for strategy_id, strategy_name, payload_json in cursor.fetchall():
        if strategy_name not in screener_mapping:
            print(f"⚠️  No mapping found for: {strategy_name}")
            skipped_count += 1
            continue

        payload = json.loads(payload_json)
        new_screener = screener_mapping[strategy_name]

        # Store old screener for comparison
        old_screener = payload.get("screener")

        # Update screener config
        payload["screener"] = new_screener

        if dry_run:
            print(f"\n{strategy_name}:")
            print(f"  Old: {old_screener}")
            print(f"  New: {new_screener}")
        else:
            cursor.execute(
                "UPDATE strategies SET payload = ? WHERE id = ?",
                (json.dumps(payload), strategy_id)
            )
            updated_count += 1

    if not dry_run:
        conn.commit()
        print(f"\n✓ Updated {updated_count} strategies")
        if skipped_count > 0:
            print(f"⚠️  Skipped {skipped_count} strategies (no mapping found)")
    else:
        print(f"\n[DRY RUN] Would update {len(screener_mapping) - skipped_count} strategies")
        if skipped_count > 0:
            print(f"[DRY RUN] Would skip {skipped_count} strategies (no mapping found)")

    conn.close()


def main() -> None:
    """Main function."""
    import argparse
    parser = argparse.ArgumentParser(description="Update strategy screener configurations")
    parser.add_argument(
        "--execute", action="store_true", help="Actually update database (default is dry-run)"
    )
    args = parser.parse_args()

    db_path = Path(__file__).parent.parent / "folios_v2.db"

    if args.execute:
        response = input("⚠️  This will modify the database. Are you sure? (yes/no): ")
        if response.lower() != "yes":
            print("Aborted.")
            return

    update_screeners(str(db_path), dry_run=not args.execute)


if __name__ == "__main__":
    main()
