UV ?= uv

.PHONY: format lint lint-fix typecheck test coverage check build ci harvest submit-stale

format:
	$(UV) run black src tests scripts

lint:
	$(UV) run ruff check src tests scripts

lint-fix:
	$(UV) run ruff check src tests scripts --fix --unsafe-fixes

typecheck:
	$(UV) run mypy src

test:
	$(UV) run pytest

coverage:
	$(UV) run pytest --cov=folios_v2 --cov-report=term

check: lint typecheck test
	@echo "All checks passed"

build:
	$(UV) pip install -q build && $(UV) run python -m build

ci: check coverage build
	@echo "CI workflow (lint/typecheck/test/coverage/build) completed"

harvest:
	$(UV) run python scripts/harvest.py

submit-stale:
	$(UV) run python scripts/submit_stale_strategies.py
