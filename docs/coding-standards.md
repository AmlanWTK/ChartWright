# Coding Standards

Consistent, boring, safe code. Tooling enforces most of this automatically; this doc captures the intent and the things tools can't check.

## Principles

1. **Clarity over cleverness.** Code is read far more than written.
2. **Types are documentation.** Strict typing on both sides (mypy strict, TS strict).
3. **Small, idempotent, testable units.** Especially pipeline workers (ADR-0001).
4. **Fail loud in dev, degrade gracefully in prod.** Structured errors, no silent catches.
5. **No PHI, ever, outside its controlled path.** Not in logs, tests, or fixtures.

## Python

- **Version:** 3.12. **Formatter/linter:** Ruff (config in root `pyproject.toml`). **Types:** mypy strict.
- Public functions/methods have full type annotations and a docstring explaining *why*, not *what*.
- Prefer `pathlib` over `os.path`; prefer f-strings; prefer dataclasses/Pydantic models over ad-hoc dicts.
- Validate all external input with Pydantic at the boundary.
- No bare `except:`; catch specific exceptions; never swallow errors silently.
- Security (Ruff `S` / bandit): no `assert` for control flow in prod code, no `subprocess` with `shell=True`, no hardcoded secrets.
- Tests: pytest, arrange-act-assert, one behavior per test, no network unless marked `integration`.

## TypeScript / Frontend

- **Version:** TS 5.5, Node 20. **Linter:** ESLint (flat config). **Formatter:** Prettier.
- `strict` + `noUncheckedIndexedAccess`. Explicit return types on exported functions.
- No `any` (use `unknown` + narrowing). No `console.log` (use `warn`/`error`).
- Components and modules are small and testable; business logic lives outside React components where practical.
- **No PHI in browser storage**; sensitive data is memory-only and cleared on logout (enforced from CP23).

## Naming & structure

- Files/modules: `snake_case.py`, `kebab-or-camel` for TS per ecosystem norms.
- Service layout: `src/<pkg>/` for code, `tests/` for tests, a `README.md` per service.
- One responsibility per module; avoid cross-service shared DB tables (integrate via API/events — ADR-0004).

## Errors & logging

- Structured logs (JSON) with correlation + tenant IDs; **never** log PHI or secrets.
- Every error carries enough context to debug (IDs, stage) without sensitive data.
- Use the shared observability helpers (from CP06) so tracing/metrics/logging are consistent.

## Commits & PRs

- Conventional Commits (enforced). One logical change per commit where practical.
- PRs stay within the current checkpoint's scope. Fill the PR template; keep CI green.

## Testing expectations

- Coverage gate: ≥ 80% on core services, 100% on critical paths (payment/PHI/decision logic).
- Deterministic tests; seed randomness; no reliance on wall-clock or network unless marked.
- AI components additionally gated by the eval harness (from CP26).

## Documentation

- Public APIs documented (OpenAPI from CP21). Non-trivial decisions get an ADR.
- Keep `docs/` in sync: diagrams (Mermaid), roadmap status, traceability.
