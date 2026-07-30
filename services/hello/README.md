# hello service

A minimal FastAPI reference service. Its only purpose is to prove the Python CI lane — linting (ruff), type-checking (mypy, strict), tests (pytest), and coverage — with the health/readiness probe pattern every Chartwright service will use.

It contains **no business logic and never touches PHI**. Real services arrive from CP06 (which turns this into the reusable service template) onward.

## Run locally

```bash
uv sync --all-groups
uv run uvicorn hello.main:app --reload --port 8000
# then open http://localhost:8000/docs
```

## Endpoints

| Path | Purpose |
|------|---------|
| `GET /healthz` | Liveness probe |
| `GET /readyz` | Readiness probe (real services also check dependencies) |
| `GET /` | Human-friendly root pointer |

## Test

```bash
uv run pytest services/hello --cov=hello --cov-report=term-missing
```
