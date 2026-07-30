# Chartwright task runner.
# Unix/macOS/WSL/Git-Bash: use `make <target>`.
# Windows PowerShell without make: run the underlying commands (shown per target)
# or use the equivalents documented in CONTRIBUTING.md.

.DEFAULT_GOAL := help
.PHONY: help setup lint format typecheck test build security precommit clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

setup: ## Install all Python + Node dependencies and pre-commit hooks
	uv sync --all-groups
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

clean: ## Remove caches and build artifacts
	rm -rf .pytest_cache .ruff_cache .mypy_cache .coverage htmlcov
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
