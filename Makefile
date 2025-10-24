UV ?= uv
DB ?= folios_v2.db
PROVIDERS ?= openai,gemini,anthropic
BALANCE ?= 100000
LINT_PATHS ?= src tests
CLI_LIMIT ?= 20

.PHONY: format lint lint-fix typecheck test coverage check build ci
.PHONY: list-strategies plan-strategies weekday-strategies today-strategies enqueue-strategies submit-batch submit-cli submit-batch-jobs poll-batch-status harvest-batch-results harvest execute execute-cli execute-ready status workflow refresh-portfolios
.PHONY: submit-stale
.PHONY: gemini-submit gemini-status gemini-harvest check-batch-status
.PHONY: generate-html generate-email publish-html

# Development commands
format:
	$(UV) run black src tests scripts

lint:
	$(UV) run ruff check $(LINT_PATHS)

lint-fix:
	$(UV) run ruff check $(LINT_PATHS) --fix --unsafe-fixes

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

plan-strategies:
	@echo "Planning strategies needing research..."
	$(UV) run python scripts/plan_strategies.py --providers "$(PROVIDERS)"

# Weekday roster helpers
weekday-strategies:
	@echo "Listing strategies for configured weekday/date..."
	$(UV) run python scripts/get_today_strategies.py $(if $(DATE),--target-date $(DATE)) $(if $(DAY),--force-weekday $(DAY)) $(if $(QUIET),--quiet)

today-strategies:
	@echo "Listing strategies scheduled for today..."
	$(UV) run python scripts/get_today_strategies.py $(if $(QUIET),--quiet)

# Submit batch requests for all active strategies
enqueue-strategies:
	@echo "Enqueueing batch requests to providers: $(PROVIDERS)"
	$(UV) run python scripts/submit_batch_requests.py --providers "$(PROVIDERS)" $(if $(STRATEGY_ID),--strategy-id "$(STRATEGY_ID)") $(if $(STRATEGY_IDS),--strategy-ids "$(STRATEGY_IDS)") $(if $(STRATEGY_FILE),--strategy-file "$(STRATEGY_FILE)") $(if $(WEEKDAY),--weekday $(WEEKDAY))

submit-batch: enqueue-strategies

# Submit batch requests for a specific strategy
submit-strategy:
	@test -n "$(STRATEGY_ID)" || (echo "Error: STRATEGY_ID is required. Use: make submit-strategy STRATEGY_ID=xxx" && exit 1)
	@echo "Submitting batch request for strategy: $(STRATEGY_ID)"
	$(UV) run python scripts/submit_batch_requests.py --strategy-id "$(STRATEGY_ID)" --providers "$(PROVIDERS)"

submit-cli:
	@echo "Submitting CLI requests for providers: $(PROVIDERS)"
	$(UV) run python scripts/submit_cli_requests.py --providers "$(PROVIDERS)" $(if $(STRATEGY_ID),--strategy-id "$(STRATEGY_ID)") $(if $(STRATEGY_IDS),--strategy-ids "$(STRATEGY_IDS)") $(if $(STRATEGY_FILE),--strategy-file "$(STRATEGY_FILE)") $(if $(WEEKDAY),--weekday $(WEEKDAY))

submit-batch-jobs:
	@echo "Submitting provider jobs for pending batch requests..."
	$(UV) run python scripts/submit_batch_jobs.py --providers "$(PROVIDERS)"

poll-batch-status:
	@echo "Polling provider status for running batch jobs..."
	$(UV) run python scripts/poll_batch_status.py --providers "$(PROVIDERS)"

# Harvest completed requests and process results
harvest-batch-results:
	@echo "Harvesting batch and CLI results..."
	$(UV) run python scripts/harvest.py

harvest: harvest-batch-results

# Execute recommendations (place trades)
execute:
	@echo "Executing recommendations..."
	$(UV) run python scripts/execute_recommendations.py

execute-cli:
	@echo "Executing pending CLI requests..."
	$(UV) run python scripts/execute_cli_requests.py --providers "$(PROVIDERS)" --limit $(CLI_LIMIT)

execute-ready:
	@echo "Executing ready portfolios..."
	$(UV) run python -m scripts.execute_ready --providers "$(PROVIDERS)" --initial-balance $(BALANCE)

# Run harvest + execute pass sequentially
refresh-portfolios:
	@echo "Refreshing portfolios (harvest + execute-ready)..."
	@$(MAKE) harvest-batch-results
	@echo
	@$(MAKE) execute-ready PROVIDERS="$(PROVIDERS)" BALANCE=$(BALANCE)

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
	@echo "[1/5] Enqueueing batch requests..."
	@make enqueue-strategies PROVIDERS="$(PROVIDERS)"
	@echo
	@echo "[2/5] Submitting provider jobs..."
	@make submit-batch-jobs PROVIDERS="$(PROVIDERS)"
	@echo
	@echo "[3/5] Polling provider status..."
	@make poll-batch-status PROVIDERS="$(PROVIDERS)"
	@echo
	@echo "[4/5] Harvesting results..."
	@make harvest-batch-results
	@echo
	@echo "[5/5] Executing recommendations..."
	@make execute-ready PROVIDERS="$(PROVIDERS)" BALANCE=$(BALANCE)
	@echo
	@echo "Workflow complete!"

# Quick workflow for testing (fewer providers, shorter wait)
workflow-quick:
	@echo "Running quick workflow with OpenAI only"
	@make submit-batch PROVIDERS="openai"
	@sleep 15
	@make harvest
	@make execute

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
	@echo "Harvesting completed Gemini batches (uses unified harvest)..."
	@echo "============================================================="
	@make harvest-batch-results

# Batch status checking (OpenAI and Gemini)
check-batch-status:
	@echo "OpenAI Batch Status:"
	@echo "===================="
	@$(UV) run python scripts/check_batch_status.py local
	@echo
	@echo "Gemini Batch Status:"
	@echo "===================="
	@$(UV) run python scripts/check_gemini_batch.py local

# HTML generation
generate-html:
	@echo "Generating public HTML files..."
	@echo "================================"
	$(UV) run python -m scripts.generate_public_html --db $(DB) --out public/

generate-email:
	@echo "Generating weekly email digest..."
	@echo "=================================="
	$(UV) run python -m scripts.generate_weekly_email --db $(DB) --out public/email

publish-html: generate-html generate-email
	@echo "✅ HTML files generated in public/"

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
	@echo "  make plan-strategies          - Show strategies needing research"
	@echo "  make weekday-strategies DAY=1 - List strategies scheduled for weekday (1=Mon)"
	@echo "  make today-strategies         - List strategies scheduled for today"
	@echo "  make enqueue-strategies       - Queue batch requests for all strategies"
	@echo "  make submit-batch             - Alias for enqueue-strategies"
	@echo "  make submit-strategy STRATEGY_ID=xxx - Submit batch for specific strategy"
	@echo "  make submit-cli               - Enqueue CLI requests (supports STRATEGY_IDS/FILE/WEEKDAY)"
	@echo "  make submit-batch-jobs        - Submit queued batch jobs to providers"
	@echo "  make poll-batch-status        - Poll running batch requests"
	@echo "  make harvest-batch-results    - Download results and finalize requests"
	@echo "  make execute-cli              - Execute pending CLI requests"
	@echo "  make execute-ready            - Execute portfolios for completed requests"
	@echo "  make harvest                  - Alias for harvest-batch-results"
	@echo "  make execute                  - Execute single request (legacy)"
	@echo "  make status                   - Show request status"
	@echo "  make submit-stale             - Submit stale strategies (>48h)"
	@echo
	@echo "Workflows:"
	@echo "  make workflow                 - Full staged workflow"
	@echo "  make workflow-quick           - Quick test with OpenAI only"
	@echo "  make refresh-portfolios       - Harvest then execute-ready in one pass"
	@echo
	@echo "Gemini Batch Operations (24+ hour processing):"
	@echo "  make gemini-submit            - Submit one Gemini batch request"
	@echo "  make gemini-status            - Check status of Gemini batch jobs"
	@echo "  make gemini-harvest           - Harvest completed Gemini batches"
	@echo
	@echo "Batch Monitoring:"
	@echo "  make check-batch-status       - Show OpenAI and Gemini batch status"
	@echo
	@echo "HTML Generation:"
	@echo "  make generate-html            - Generate public HTML files (leaderboard, strategies, feed)"
	@echo "  make generate-email           - Generate weekly email digest"
	@echo "  make publish-html             - Generate all HTML outputs"
	@echo
	@echo "Configuration:"
	@echo "  PROVIDERS=openai,gemini,anthropic - Set providers (default: all)"
	@echo "  DB=folios_v2.db                   - Set database file"
	@echo
	@echo "Examples:"
	@echo "  make submit-batch PROVIDERS=openai"
	@echo "  make submit-strategy STRATEGY_ID=strategy_bd6b5423"
	@echo "  make workflow PROVIDERS=gemini,anthropic"
