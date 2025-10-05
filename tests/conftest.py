from __future__ import annotations

import sys
from pathlib import Path

# Ensure the src/ directory is importable when tests run via `uv run pytest`.
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
