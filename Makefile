UV ?= uv
DB ?= folios_v2.db
PROVIDERS ?= openai,gemini,anthropic

.PHONY: format lint lint-fix typecheck test coverage check build ci
.PHONY: list-strategies submit harvest execute status workflow
.PHONY: submit-batch submit-cli submit-stale test-cli
.PHONY: gemini-submit gemini-status gemini-harvest check-batch-status

# Development commands
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

# Strategy operations
list-strategies:
	@echo "Active Strategies:"
	@echo "=================="
	$(UV) run python -m folios_v2.cli list-strategies

# Submit batch requests for all active strategies
submit-batch:
	@echo "Submitting batch requests to providers: $(PROVIDERS)"
	$(UV) run python scripts/submit_batch_requests.py --providers "$(PROVIDERS)"

# Submit batch requests for a specific strategy
submit-strategy:
	@test -n "$(STRATEGY_ID)" || (echo "Error: STRATEGY_ID is required. Use: make submit-strategy STRATEGY_ID=xxx" && exit 1)
	@echo "Submitting batch request for strategy: $(STRATEGY_ID)"
	$(UV) run python scripts/submit_batch_requests.py --strategy-id "$(STRATEGY_ID)" --providers "$(PROVIDERS)"

# Harvest completed requests and process results
harvest:
	@echo "Harvesting completed requests..."
	$(UV) run python scripts/harvest.py

# Execute recommendations (place trades)
execute:
	@echo "Executing recommendations..."
	$(UV) run python scripts/execute_recommendations.py

# Show status of pending/completed requests
status:
	@echo "Request Status:"
	@echo "==============="
	@$(UV) run python scripts/show_status.py

# Submit stale strategies (>48 hours without submissions)
submit-stale:
	@echo "Submitting stale strategies..."
	$(UV) run python scripts/submit_stale_strategies.py

# Complete workflow: submit -> harvest -> execute
workflow:
	@echo "Running complete workflow: submit -> harvest -> execute"
	@echo "========================================================"
	@echo
	@echo "[1/3] Submitting batch requests..."
	@make submit-batch PROVIDERS="$(PROVIDERS)"
	@echo
	@echo "[2/3] Waiting 30 seconds for processing..."
	@sleep 30
	@echo
	@echo "[3/3] Harvesting results..."
	@make harvest
	@echo
	@echo "[4/4] Executing recommendations..."
	@make execute
	@echo
	@echo "Workflow complete!"

# Quick workflow for testing (fewer providers, shorter wait)
workflow-quick:
	@echo "Running quick workflow with OpenAI only"
	@make submit-batch PROVIDERS="openai"
	@sleep 15
	@make harvest
	@make execute

# Test CLI executors with 5 random strategies
test-cli:
	@echo "Testing CLI executors with 5 strategies across all providers"
	@echo "============================================================="
	$(UV) run python scripts/run_cli_test.py

# Gemini batch operations (24+ hour processing time)
gemini-submit:
	@echo "Submitting Gemini batch request..."
	@echo "===================================="
	$(UV) run python scripts/test_gemini_submit.py

gemini-status:
	@echo "Checking Gemini batch status..."
	@echo "================================"
	$(UV) run python scripts/check_gemini_batch.py status

gemini-harvest:
	@echo "Harvesting completed Gemini batches..."
	@echo "======================================="
	$(UV) run python scripts/harvest_gemini_batches.py

# Batch status checking (OpenAI and Gemini)
check-batch-status:
	@echo "OpenAI Batch Status:"
	@echo "===================="
	@$(UV) run python scripts/check_batch_status.py local
	@echo
	@echo "Gemini Batch Status:"
	@echo "===================="
	@$(UV) run python scripts/check_gemini_batch.py local

# Help command
help:
	@echo "Folios v2 - Available Make Targets"
	@echo "==================================="
	@echo
	@echo "Development:"
	@echo "  make format        - Format code with black"
	@echo "  make lint          - Check code with ruff"
	@echo "  make lint-fix      - Auto-fix linting issues"
	@echo "  make typecheck     - Run mypy type checking"
	@echo "  make test          - Run pytest tests"
	@echo "  make coverage      - Run tests with coverage"
	@echo "  make check         - Run all checks (lint + typecheck + test)"
	@echo "  make build         - Build distribution packages"
	@echo "  make ci            - Run full CI workflow"
	@echo
	@echo "Strategy Operations:"
	@echo "  make list-strategies          - List all active strategies"
	@echo "  make submit-batch             - Submit batch requests for all strategies"
	@echo "  make submit-strategy STRATEGY_ID=xxx - Submit batch for specific strategy"
	@echo "  make harvest                  - Harvest completed requests"
	@echo "  make execute                  - Execute trade recommendations"
	@echo "  make status                   - Show request status"
	@echo "  make submit-stale             - Submit stale strategies (>48h)"
	@echo
	@echo "Workflows:"
	@echo "  make workflow                 - Full workflow: submit → harvest → execute"
	@echo "  make workflow-quick           - Quick test with OpenAI only"
	@echo "  make test-cli                 - Test CLI executors with 5 strategies"
	@echo
	@echo "Gemini Batch Operations (24+ hour processing):"
	@echo "  make gemini-submit            - Submit one Gemini batch request"
	@echo "  make gemini-status            - Check status of Gemini batch jobs"
	@echo "  make gemini-harvest           - Harvest completed Gemini batches"
	@echo
	@echo "Batch Monitoring:"
	@echo "  make check-batch-status       - Show OpenAI and Gemini batch status"
	@echo
	@echo "Configuration:"
	@echo "  PROVIDERS=openai,gemini,anthropic - Set providers (default: all)"
	@echo "  DB=folios_v2.db                   - Set database file"
	@echo
	@echo "Examples:"
	@echo "  make submit-batch PROVIDERS=openai"
	@echo "  make submit-strategy STRATEGY_ID=strategy_bd6b5423"
	@echo "  make workflow PROVIDERS=gemini,anthropic"
