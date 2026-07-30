"""Alembic environment: migrations run online against the admin URL."""

from __future__ import annotations

from alembic import context
from chartwright_db.models import Base
from chartwright_db.session import admin_database_url
from sqlalchemy import create_engine

target_metadata = Base.metadata


def run_migrations_online() -> None:
    engine = create_engine(admin_database_url())
    with engine.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    msg = "Offline migrations are not supported; run against a live database."
    raise RuntimeError(msg)

run_migrations_online()
