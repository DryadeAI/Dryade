# Dryade -- Community Workflow
# ============================
# Usage: make <target>
# Run `make help` to see all available targets with descriptions.

.DEFAULT_GOAL := help

.PHONY: help setup start start-gpu stop test dev build logs clean ci-local ci-lint ci-test

# -- Self-documentation -------------------------------------------------------

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

# -- Onboarding ---------------------------------------------------------------

setup: ## First-time setup: copy env, install deps
	@test -f .env || cp .env.example .env
	@echo ""
	@echo "Setup complete! Edit .env with your configuration, then run 'make start'"

# -- Services ------------------------------------------------------------------

start: ## Start all services with Docker Compose
	docker compose up -d
	@echo "Dryade is running at http://localhost:8080 (API) and http://localhost:3000 (UI)"

start-gpu: ## Start all services including vLLM (requires NVIDIA GPU)
	docker compose --profile gpu up -d

stop: ## Stop all services
	docker compose down

dev: ## Start in development mode with hot-reload
	docker compose up

build: ## Build Docker images
	docker compose build

logs: ## View service logs
	docker compose logs -f

# -- Quality -------------------------------------------------------------------

test: ## Run backend tests
	docker compose exec dryade pytest tests/ -v --timeout=120

# -- Local CI ------------------------------------------------------------------

ci-local: ci-lint ci-test ## Run local CI checks (mirrors GitHub Actions)
	@echo ""
	@echo "  All local CI checks passed"
	@echo ""

ci-lint: ## Lint + format check
	@echo "=== Ruff check ==="
	@PYTHONPATH=.:dryade-core .venv/bin/ruff check dryade-core/core/
	@echo "=== Ruff format ==="
	@PYTHONPATH=.:dryade-core .venv/bin/ruff format --check dryade-core/core/ || echo "Format differences (non-blocking)"

ci-test: ## Run unit + integration tests
	@echo "=== Unit tests ==="
	@PYTHONPATH=.:dryade-core .venv/bin/pytest tests/unit/ -m "not e2e" \
		--ignore=tests/eval --timeout=120 -q
	@echo "=== Integration tests ==="
	@PYTHONPATH=.:dryade-core .venv/bin/pytest tests/integration/ -m "not e2e" \
		--ignore=tests/integration/workflows --ignore=tests/eval --timeout=120 -q

# -- Cleanup -------------------------------------------------------------------

clean: ## Stop services and remove volumes
	docker compose down -v
