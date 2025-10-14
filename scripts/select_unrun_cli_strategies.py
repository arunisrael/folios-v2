"""Select random strategies not run via Gemini CLI."""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path

# Path to database
db_path = Path(__file__).parent.parent / "folios_v2.db"

# Connect to database
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# Get all active strategies
cursor.execute("SELECT id, name FROM strategies WHERE status = 'active' ORDER BY name")
all_strategies = cursor.fetchall()

# Get strategies that have been run with Gemini CLI
cursor.execute("""
    SELECT DISTINCT strategy_id
    FROM requests
    WHERE provider_id = 'gemini' AND mode = 'cli'
""")
run_strategies = {row[0] for row in cursor.fetchall()}

# Filter to unrun strategies
unrun_strategies = [
    (sid, name) for sid, name in all_strategies if sid not in run_strategies
]

print(f"Total active strategies: {len(all_strategies)}")
print(f"Already run with Gemini CLI: {len(run_strategies)}")
print(f"Unrun strategies: {len(unrun_strategies)}")
print()

# Select 10 random strategies
if len(unrun_strategies) >= 10:
    selected = random.sample(unrun_strategies, 10)
else:
    selected = unrun_strategies
    print(f"Note: Only {len(unrun_strategies)} unrun strategies available")

print(f"Selected {len(selected)} strategies:")
print()
for sid, name in selected:
    print(f"{sid}|{name}")

# Close connection
conn.close()
