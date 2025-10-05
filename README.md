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

# Run formatting, typing, and tests
ruff check .
black --check .
mypy .
pytest
```

## Project Layout (in progress)
```
folios-v2/
├── docs/               # Requirements capture and architecture notes
├── src/folios_v2/      # Application source (domain, providers, runtime, orchestration, cli)
└── tests/              # Pytest suites
```

Implementation proceeds in phases; see `docs/requirements.md` for the captured scope and design targets.
