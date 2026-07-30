# Chartwright task runner.
# Unix/macOS/WSL/Git-Bash: use `make <target>`.
# Windows PowerShell without make: run the underlying commands (shown per target)
# or use the equivalents documented in CONTRIBUTING.md.

.DEFAULT_GOAL := help
.PHONY: help setup lint format typecheck test build security precommit clean local-up local-down local-nuke local-check db-upgrade db-downgrade db-seed test-integration

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Install all Python + Node dependencies and pre-commit hooks
	uv sync --all-packages --all-groups
	pnpm install
	pre-commit install --install-hooks
	pre-commit install --hook-type commit-msg

lint: ## Lint Python (ruff) and frontend (eslint)
	uv run ruff check .
	pnpm run lint

format: ## Auto-format Python (ruff) and frontend (prettier)
	uv run ruff format .
	uv run ruff check --fix .
	pnpm run format

format-check: ## Check formatting without changing files
	uv run ruff format --check .
	pnpm run format:check

typecheck: ## Type-check Python (mypy) and frontend (tsc)
	uv run mypy
	pnpm run typecheck

test: ## Run Python (pytest+coverage) and frontend (vitest) tests
	uv run pytest --cov --cov-report=term-missing
	pnpm run test

build: ## Build frontend workspace packages
	pnpm run build

security: ## Run local secret scan (gitleaks must be installed)
	gitleaks detect --no-banner --redact

precommit: ## Run all pre-commit hooks against all files
	pre-commit run --all-files

local-up: ## Start the local dev platform (Postgres, Kafka, Temporal, Redis, MinIO)
	docker compose -f infra/local/docker-compose.yml up -d

local-down: ## Stop the local dev platform (data preserved)
	docker compose -f infra/local/docker-compose.yml down

local-nuke: ## Stop the local dev platform AND delete all data volumes
	docker compose -f infra/local/docker-compose.yml down -v

local-check: ## Smoke-check every local service
	uv run python scripts/check_local_stack.py

db-upgrade: ## Apply database migrations (admin role)
	cd libs/chartwright-db && uv run alembic upgrade head

db-downgrade: ## Roll back the last migration
	cd libs/chartwright-db && uv run alembic downgrade -1

db-seed: ## Seed demo tenants + synthetic documents
	uv run python scripts/seed_dev_db.py

test-integration: ## Run integration tests (requires local stack + migrations)
	uv run pytest -m integration

run-ingestion: ## Run the ingestion service locally (port 8100)
	uv run uvicorn ingestion.main:app --reload --port 8100

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
