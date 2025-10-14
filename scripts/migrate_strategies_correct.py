#!/usr/bin/env python3
"""
Corrected migration script to transfer strategies from folios-py to folios-v2.
Properly maps old schema to new schema with UUID generation and field transformations.
"""

import json
import sqlite3
import sys
from datetime import datetime
from typing import Any
from uuid import uuid4


class StrategyMigrator:
    def __init__(self, source_db: str, target_db: str, batch_size: int = 5) -> None:
        self.source_db = source_db
        self.target_db = target_db
        self.batch_size = batch_size
        self.migrated_count = 0
        self.failed_ids = []
        self.id_mapping = {}  # old_id -> new_uuid

    def connect_source(self) -> sqlite3.Connection:
        """Connect to source database (folios-py)"""
        conn = sqlite3.connect(self.source_db)
        conn.row_factory = sqlite3.Row
        return conn

    def connect_target(self) -> sqlite3.Connection:
        """Connect to target database (folios-v2)"""
        conn = sqlite3.connect(self.target_db)
        return conn

    def extract_strategies(self, offset: int, limit: int) -> list[dict[str, Any]]:
        """Extract batch of strategies from source database"""
        conn = self.connect_source()
        cursor = conn.cursor()

        query = """
        SELECT
            id, name, prompt, tickers, user_id, status,
            risk_controls, metadata, screener, schedule,
            options_enabled, short_enabled, is_active, is_live,
            initial_capital_usd, portfolio_value_usd, performance,
            created_at, updated_at
        FROM strategies
        ORDER BY created_at
        LIMIT ? OFFSET ?
        """

        cursor.execute(query, (limit, offset))
        rows = cursor.fetchall()
        conn.close()

        strategies = []
        for row in rows:
            strategy = dict(row)
            # Parse JSON fields
            for field in ['tickers', 'risk_controls', 'metadata', 'screener', 'performance']:
                if strategy[field]:
                    try:
                        strategy[field] = json.loads(strategy[field])
                    except (json.JSONDecodeError, TypeError):
                        strategy[field] = None

            strategies.append(strategy)

        return strategies

    def transform_metadata(self, old_metadata: dict[str, Any] | None) -> dict[str, Any] | None:
        """Transform old metadata structure to new structure"""
        if not old_metadata:
            return None

        # Map category → theme, drop extra fields
        new_metadata = {
            "description": old_metadata.get("description", ""),
            "theme": old_metadata.get("category"),  # category → theme
            "risk_level": old_metadata.get("risk_level"),
            "time_horizon": old_metadata.get("time_horizon"),
            "key_metrics": tuple(old_metadata.get("key_metrics", [])) if old_metadata.get("key_metrics") else None,
            "key_signals": tuple(old_metadata.get("key_signals", [])) if old_metadata.get("key_signals") else None,
        }

        # Remove None values for optional fields
        return {k: v for k, v in new_metadata.items() if v is not None or k == "description"}

    def transform_screener(self, old_screener: dict[str, Any] | None) -> dict[str, Any] | None:
        """Transform old screener structure to new structure"""
        if not old_screener:
            return None

        # Drop 'rationale', keep everything else
        new_screener = {
            "enabled": old_screener.get("enabled", True),
            "provider": old_screener.get("provider"),
            "limit": old_screener.get("limit", 25),
            "filters": old_screener.get("filters", {}),
            "universe_cap": None,  # New field, set to None
        }

        return new_screener

    def validate_risk_controls(self, risk_controls: dict[str, Any] | None) -> dict[str, Any] | None:
        """Validate and clean risk controls"""
        if not risk_controls:
            return None

        # Ensure percentage values are within valid range (0-100)
        validated = {}
        for key in ['max_position_size', 'max_exposure', 'stop_loss', 'max_short_exposure', 'max_single_name_short']:
            value = risk_controls.get(key)
            if value is not None:
                # Clamp to 0-100 range
                validated[key] = max(0.0, min(100.0, float(value)))
            else:
                validated[key] = None

        # Handle other fields
        validated['max_leverage'] = risk_controls.get('max_leverage')
        validated['borrow_available'] = risk_controls.get('borrow_available')

        return validated

    def transform_strategy(self, old_strategy: dict[str, Any]) -> dict[str, Any]:
        """Transform old schema to new Strategy model structure"""

        # Generate new UUID for this strategy
        new_id = str(uuid4())
        old_id = old_strategy["id"]
        self.id_mapping[old_id] = new_id

        # Parse and transform complex fields
        metadata = self.transform_metadata(old_strategy.get("metadata"))
        screener = self.transform_screener(old_strategy.get("screener"))
        risk_controls = self.validate_risk_controls(old_strategy.get("risk_controls"))

        # Build complete Strategy payload matching v2 schema
        payload = {
            "id": new_id,  # New UUID
            "name": old_strategy["name"],
            "prompt": old_strategy["prompt"],
            "tickers": old_strategy["tickers"] or [],
            "status": "active" if old_strategy.get("is_active") else old_strategy.get("status", "draft"),
            "risk_controls": risk_controls,
            "metadata": metadata,
            "preferred_providers": [],  # New field, empty array
            "active_modes": ["batch"],  # New field, default to batch
            "screener": screener,
            "research_day": 4,  # Default to Thursday (could parse from schedule)
            "research_time_utc": None,  # New field, null
            "runtime_weight": 1.0,  # New field, default weight
            "created_at": old_strategy.get("created_at", datetime.utcnow().isoformat() + "Z"),
            "updated_at": old_strategy.get("updated_at", datetime.utcnow().isoformat() + "Z"),
        }

        # Ensure timestamps are in ISO format with Z
        for ts_field in ['created_at', 'updated_at']:
            if payload[ts_field] and not payload[ts_field].endswith('Z'):
                # Add Z if missing
                payload[ts_field] = payload[ts_field].replace(' ', 'T') + 'Z' if 'T' not in payload[ts_field] else payload[ts_field] + 'Z'

        return {
            "id": new_id,
            "name": old_strategy["name"],
            "status": payload["status"],
            "payload": payload,
            "old_id": old_id,  # Keep for reference
        }

    def load_strategy(self, conn: sqlite3.Connection, strategy: dict[str, Any]) -> bool:
        """Load single strategy into target database"""
        try:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO strategies (id, name, status, payload)
                VALUES (?, ?, ?, ?)
                """,
                (
                    strategy["id"],
                    strategy["name"],
                    strategy["status"],
                    json.dumps(strategy["payload"])
                )
            )
            return True
        except sqlite3.IntegrityError:
            print(f"  ⚠️  Skipping duplicate: {strategy['old_id']} → {strategy['id']} ({strategy['name']})")
            return False
        except Exception as e:
            print(f"  ❌ Error inserting {strategy['old_id']} → {strategy['id']}: {e}")
            return False

    def validate_batch(self, conn: sqlite3.Connection, strategy_ids: list[str]) -> bool:
        """Validate that all strategies in batch were inserted correctly"""
        cursor = conn.cursor()
        placeholders = ','.join('?' * len(strategy_ids))
        cursor.execute(
            f"SELECT COUNT(*) FROM strategies WHERE id IN ({placeholders})",
            strategy_ids
        )
        count = cursor.fetchone()[0]
        return count == len(strategy_ids)

    def get_total_count(self) -> int:
        """Get total number of strategies to migrate"""
        conn = self.connect_source()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM strategies")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def get_target_count(self) -> int:
        """Get current count in target database"""
        conn = self.connect_target()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM strategies")
        count = cursor.fetchone()[0]
        conn.close()
        return count

    def migrate(self, dry_run: bool = False) -> None:
        """Execute migration in batches"""
        total = self.get_total_count()
        target_count = self.get_target_count()

        print(f"{'=' * 80}")
        print("Strategy Migration: folios-py → folios-v2 (CORRECTED)")
        print(f"{'=' * 80}")
        print(f"Source: {self.source_db}")
        print(f"Target: {self.target_db}")
        print(f"Total strategies to migrate: {total}")
        print(f"Current target count: {target_count}")
        print(f"Batch size: {self.batch_size}")
        print(f"Dry run: {dry_run}")
        print(f"{'=' * 80}\n")

        if dry_run:
            print("🔍 DRY RUN MODE - No data will be written\n")

        offset = 0
        batch_num = 1

        while offset < total:
            print(f"📦 Batch {batch_num} (strategies {offset + 1}-{min(offset + self.batch_size, total)})")

            # Extract
            strategies = self.extract_strategies(offset, self.batch_size)
            if not strategies:
                break

            print(f"  Extracted {len(strategies)} strategies")

            # Transform
            transformed = []
            for strat in strategies:
                try:
                    transformed_strat = self.transform_strategy(strat)
                    transformed.append(transformed_strat)
                    print(f"    ✓ {strat['id']} → {transformed_strat['id']}: {strat['name']}")
                except Exception as e:
                    print(f"    ❌ Failed to transform {strat['id']}: {e}")
                    self.failed_ids.append(strat['id'])

            # Load (if not dry run)
            if not dry_run and transformed:
                conn = self.connect_target()
                successfully_loaded = []

                for strat in transformed:
                    if self.load_strategy(conn, strat):
                        successfully_loaded.append(strat['id'])
                        self.migrated_count += 1

                conn.commit()

                # Validate
                if successfully_loaded:
                    if self.validate_batch(conn, successfully_loaded):
                        print(f"  ✅ Batch {batch_num} validated: {len(successfully_loaded)} strategies inserted")
                    else:
                        print(f"  ⚠️  Batch {batch_num} validation failed!")

                conn.close()
            elif dry_run:
                print(f"  🔍 Would insert {len(transformed)} strategies (dry run)")
                self.migrated_count += len(transformed)

            print()
            offset += self.batch_size
            batch_num += 1

        # Summary
        print(f"{'=' * 80}")
        print("Migration Summary")
        print(f"{'=' * 80}")
        print(f"Total processed: {self.migrated_count}")
        print(f"Failed: {len(self.failed_ids)}")
        if self.failed_ids:
            print(f"Failed IDs: {', '.join(self.failed_ids)}")
        print(f"{'=' * 80}")

        if not dry_run:
            final_count = self.get_target_count()
            print(f"Target database now contains: {final_count} strategies")

            # Save ID mapping for reference
            mapping_file = "strategy_id_mapping.json"
            with open(mapping_file, 'w') as f:
                json.dump(self.id_mapping, f, indent=2)
            print(f"ID mapping saved to: {mapping_file}")


def main() -> None:
    source = "/Users/arun/apps/folios-py/development.db"
    target = "/Users/arun/apps/folios-v2/folios_v2.db"

    # Default to dry run for safety
    dry_run = "--execute" not in sys.argv
    batch_size = 5

    # Allow custom batch size
    for i, arg in enumerate(sys.argv):
        if arg == "--batch-size" and i + 1 < len(sys.argv):
            batch_size = int(sys.argv[i + 1])

    migrator = StrategyMigrator(source, target, batch_size=batch_size)
    migrator.migrate(dry_run=dry_run)

    if dry_run:
        print("\n💡 Run with --execute flag to perform actual migration")
        print("   Example: python scripts/migrate_strategies_correct.py --execute")
        print("   Example: python scripts/migrate_strategies_correct.py --execute --batch-size 10")


if __name__ == "__main__":
    main()
