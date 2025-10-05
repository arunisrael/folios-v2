.PHONY: format lint typecheck test check

format:
	uv run black src tests

lint:
	uv run ruff check src tests

typecheck:
	uv run mypy src

test:
	uv run pytest

check: lint typecheck test
