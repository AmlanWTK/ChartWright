"""Harden RLS policies: treat an empty tenant setting as NULL (deny cleanly).

Revision ID: 0002
Revises: 0001

Postgres subtlety found by the CP08 integration suite: after a transaction that ran
``SET LOCAL app.current_tenant``, a pooled connection reverts the GUC to its session
value — which, for a never-set custom parameter, is the EMPTY STRING rather than NULL.
The 0001 policies then evaluate ``''::uuid`` and raise a cast error. Isolation still
held (the query failed), but the contract is deny-*cleanly*: no context -> zero rows.

``NULLIF(current_setting(...), '')`` maps the empty string to NULL, restoring the
intended behavior on fresh AND reused connections.
"""

from __future__ import annotations

from alembic import op

from chartwright_db.models import RLS_TABLES

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

_TENANT_EXPR = "NULLIF(current_setting('app.current_tenant', true), '')::uuid"


def upgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
                USING (tenant_id = {_TENANT_EXPR})
                WITH CHECK (tenant_id = {_TENANT_EXPR})
            """
        )


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS tenant_isolation_{table} ON {table}")
        op.execute(
            f"""
            CREATE POLICY tenant_isolation_{table} ON {table}
                USING (tenant_id = current_setting('app.current_tenant', true)::uuid)
                WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)
            """
        )
