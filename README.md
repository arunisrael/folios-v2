# Folios v2

Strictly typed rebuild of the Folios trading workbench. The project implements the redesigned architecture outlined in `../folios-py/docs/redesign/` with a focus on declarative provider plugins, unified request lifecycles, and a cron-friendly weekly cadence.

## Tooling
- Python >= 3.11
- `uv` / `pip` for dependency management
- `ruff`, `black`, `mypy --strict`, and `pytest`

### Quickstart
```bash
# Install dependencies (dev extras recommended during development)
uv pip install -e .[dev]

# Run the standard quality suite
make check

# Additional helpers
make lint-fix       # Ruff autofix
make coverage       # pytest coverage report
make harvest        # Execute pending requests once
make submit-stale   # Queue research for idle strategies
```

## Project Layout (in progress)
```
folios-v2/
├── docs/               # Requirements capture and architecture notes
├── scripts/            # Operational helpers (harvest, submit_stale_strategies)
├── src/folios_v2/      # Application source (domain, providers, runtime, orchestration, cli)
└── tests/              # Pytest suites
```

Implementation proceeds in phases; see `docs/requirements.md` for the captured scope and design targets.
