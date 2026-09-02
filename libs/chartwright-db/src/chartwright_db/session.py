"""Engine factory and the tenant-scoped session context (the RLS entry point).

The application NEVER opens a raw session against tenant data: it uses ``tenant_context``,
which sets ``app.current_tenant`` with ``SET LOCAL`` inside the transaction. The RLS
policies (migration 0001) key on that setting, so:

- no context  -> policies see NULL -> tenant tables appear empty;
- context = A -> only tenant A's rows exist, at the database level.

``SET LOCAL`` scopes the setting to the transaction, so pooled connections cannot leak a
tenant context between requests.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session

# Dev-only defaults matching the CP04-L local stack (host port 15432 — see compose file;
# 5432/5433 are commonly occupied by native Postgres installs). Real envs must set env vars.
_DEV_APP_URL = "postgresql+psycopg://chartwright_app:app_dev@localhost:15432/chartwright"
_DEV_ADMIN_URL = "postgresql+psycopg://chartwright:chartwright_dev@localhost:15432/chartwright"


def app_database_url() -> str:
    """URL for the RLS-constrained application role."""
    return os.environ.get("CHARTWRIGHT_DATABASE_URL", _DEV_APP_URL)


def admin_database_url() -> str:
    """URL for migrations/admin only (bypasses RLS — never use for app queries)."""
    return os.environ.get("CHARTWRIGHT_DATABASE_ADMIN_URL", _DEV_ADMIN_URL)


def build_engine(
    url: str | None = None, *, echo: bool = False, connect_timeout: int | None = None
) -> Engine:
    """Engine for ``url`` (the app role by default).

    ``connect_timeout`` bounds the TCP connect, in seconds. Without it an unreachable
    host -- a stopped container, as opposed to a refused port -- hangs for the OS
    default of several minutes. Integration-test skip guards pass a small value so a
    missing dependency is reported in seconds; the first version of those guards turned
    an 18-test skip into a 13-minute wait, which is barely better than the failure it
    replaced.
    """
    connect_args: dict[str, Any] = {}
    if connect_timeout is not None:
        connect_args["connect_timeout"] = connect_timeout
    return create_engine(
        url or app_database_url(),
        echo=echo,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


@contextmanager
def tenant_context(engine: Engine, tenant_id: uuid.UUID) -> Iterator[Session]:
    """A transaction-scoped session bound to one tenant.

    Commits on clean exit, rolls back on exception. All repository operations happen
    inside this context so the write and its audit entry share one transaction.
    """
    with Session(engine) as session, session.begin():
        # Parameter binding is not supported for SET LOCAL; validate then inline.
        # tenant_id is a uuid.UUID, so str() is guaranteed injection-safe.
        session.execute(text(f"SET LOCAL app.current_tenant = '{tenant_id!s}'"))
        yield session


@contextmanager
def no_tenant_session(engine: Engine) -> Iterator[Session]:
    """A session with NO tenant context — used by tests to prove RLS denies by default,
    and by admin flows that only touch non-RLS tables (e.g. `tenants`)."""
    with Session(engine) as session, session.begin():
        yield session
