# chartwright-db

The persistence layer (CP08): SQLAlchemy 2.0 typed models, **row-level-security tenant isolation**, **audit-on-write**, and Alembic migrations, targeting the local Postgres from CP04-L (and later RDS unchanged — connection string is config).

## The three guarantees

1. **Tenant isolation is enforced by the database, not the application.** Every tenant-owned table has RLS enabled (and `FORCE`d), with policies keyed to `current_setting('app.current_tenant')`. The application connects as the **non-superuser** role `chartwright_app` (RLS applies; the admin role would bypass it) and sets the tenant per transaction via `tenant_context()`. A query without a tenant context returns nothing; a query in tenant A's context physically cannot see tenant B's rows.
2. **Every write is audited in the same transaction.** Repositories record an append-only `audit_log` entry (actor, action, entity, before/after) atomically with the change — if the write commits, so does its audit trail.
3. **Schema changes only via migrations.** `alembic upgrade head` is the sole way schema reaches a database.

## Setup (local stack must be running: `make local-up`)

```bash
make db-upgrade      # apply migrations (creates schema + RLS + app role)
make db-seed         # demo tenants + synthetic documents/extractions
```

## Usage

```python
from chartwright_db import build_engine, tenant_context, DocumentRepository

engine = build_engine()  # reads CHARTWRIGHT_DATABASE_URL (app-role URL)
with tenant_context(engine, tenant_id) as session:
    repo = DocumentRepository(session, actor="ingestion-service")
    doc = repo.create_document(source_channel="api", content_hash="...", page_count=3)
```

## Environment

| Variable | Default (local dev) | Used by |
|----------|--------------------|---------|
| `CHARTWRIGHT_DATABASE_URL` | app-role URL to localhost:5432 | application/repositories |
| `CHARTWRIGHT_DATABASE_ADMIN_URL` | admin URL to localhost:5432 | Alembic migrations only |

Dev-only defaults are baked in for the CP04-L stack; real environments must set both explicitly.

## Tests

- **Unit** (`pytest -m "not integration"`): model invariants, no DB needed.
- **Integration** (`pytest -m integration`): requires the local stack; applies migrations, then proves **cross-tenant reads fail**, **no-context reads return nothing**, and **audit-on-write** — the CP08 acceptance tests.

CI runs unit tests only (no services in CI yet); integration runs locally and gates checkpoint completion.
