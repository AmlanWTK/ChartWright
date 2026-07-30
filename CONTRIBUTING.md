# Contributing to Chartwright

This guide covers local setup, the toolchain, and the workflow. Read `docs/working-agreements.md` and `docs/definition-of-done.md` first — they define *how* we build.

## Prerequisites

| Tool | Version | Purpose | Install |
|------|---------|---------|---------|
| Python | 3.12 | Backend services | via `uv python install 3.12` |
| uv | latest | Python deps + workspace | https://docs.astral.sh/uv/ |
| Node | 20 | Frontend toolchain | https://nodejs.org / nvm |
| pnpm | 9 | JS workspace | `corepack enable` then `corepack prepare pnpm@9 --activate` |
| pre-commit | latest | Local git hooks | `pipx install pre-commit` (or `uv tool install pre-commit`) |
| gitleaks | latest (optional) | Local secret scan | https://github.com/gitleaks/gitleaks |

## One-time setup

```bash
# from the repo root
uv sync --all-groups          # Python deps for all workspace members
pnpm install                  # Node deps
pre-commit install --install-hooks
pre-commit install --hook-type commit-msg
```

> **Windows note:** `make` may not be installed. Either run the commands below directly,
> use them via Git Bash / WSL, or install make. Every `make` target maps to explicit
> `uv`/`pnpm` commands (see the `Makefile`).

## Everyday commands

| Task | `make` | Direct |
|------|--------|--------|
| Lint | `make lint` | `uv run ruff check .` && `pnpm run lint` |
| Format | `make format` | `uv run ruff format .` && `pnpm run format` |
| Type-check | `make typecheck` | `uv run mypy` && `pnpm run typecheck` |
| Test | `make test` | `uv run pytest --cov` && `pnpm run test` |
| Build FE | `make build` | `pnpm run build` |
| All hooks | `make precommit` | `pre-commit run --all-files` |

## Repository layout

```
services/   Python backend services (each a uv workspace member)
frontend/   Frontend workspace (real review console arrives at CP23)
libs/       Shared Python libraries
infra/      Terraform + Helm (from CP04)
evals/      Eval harness + gold sets (from CP26)
docs/       Architecture, ADRs, roadmap, governance
```

## Branching & commits

- Branch per checkpoint/task: `cpNN/short-description` (e.g. `cp02/ci-foundation`).
- **Conventional Commits** are enforced (commitlint, locally + in CI):
  `type(scope): subject` — e.g. `feat(ingestion): add malware scan`.
  Allowed types: `feat, fix, docs, style, refactor, perf, test, build, ci, chore, revert`.
- Open a PR into `main`; fill the PR template; CI must be green; get review approval.

## Adding a new Python service

1. Create `services/<name>/` with a `pyproject.toml` (see `services/hello` as the template).
2. Put code in `src/<name>/`, tests in `tests/`.
3. It's picked up automatically by the uv workspace and CI's Python lane.

## Adding a frontend package

Add it under `frontend/` (workspace glob). Provide `lint`, `typecheck`, `test`, `build` scripts so root `pnpm -r` picks it up.

## Non-negotiables

- **No secrets** in code, config, or history (gitleaks blocks this).
- **No PHI** anywhere — not in code, tests, fixtures, logs, or commit messages. Use synthetic data.
- Keep each PR scoped to the current checkpoint.

## CI

Every PR runs: change detection → Python lane (ruff, mypy, pytest+coverage) → frontend lane (prettier, eslint, tsc, vitest, build) → commitlint → security (gitleaks, Trivy, Semgrep, CodeQL). Branch protection requires the aggregate `ci-ok` check.
