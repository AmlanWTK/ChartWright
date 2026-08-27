"""Multi-packet fan-out: one upload becomes N independently-routed documents.

Revision ID: 0003
Revises: 0002

CP13 splits an upload into logical packets; CP14 classified only the first and CP15
extracts per document type, so a mixed fax has to become one ``Document`` row per packet.
Deferred at CP13 and again at CP14 — landed here because extraction is the first stage
that is genuinely wrong without it.

Two columns and one index change:

1. ``parent_document_id`` — self-FK to the upload the packet came from. NULL means "this
   IS the upload" (the overwhelmingly common single-packet case takes an unchanged path).
2. ``packet_index`` — 1-based position within the parent, for stable ordering and audit.
3. **The dedupe index becomes partial.** ``ix_documents_tenant_hash`` is UNIQUE on
   ``(tenant_id, content_hash)``, and every child of an upload shares the parent's hash —
   it is literally the same bytes — so N children would violate it on insert. Dedupe is a
   property of *uploads* ("this tenant already sent this file"), not of packets, so the
   index is rebuilt with ``WHERE parent_document_id IS NULL``. Parents still dedupe
   exactly as before; children are exempt by construction.

RLS is deliberately untouched: the policies key on ``tenant_id`` alone, children inherit
their parent's tenant, and no policy expression references the new columns. Isolation is
unchanged — verified by re-running CP08's integration suite after this migration.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_DEDUPE_INDEX = "ix_documents_tenant_hash"


def upgrade() -> None:
    op.add_column(
        "documents",
        sa.Column("parent_document_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column("documents", sa.Column("packet_index", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_documents_parent_document_id",
        source_table="documents",
        referent_table="documents",
        local_cols=["parent_document_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_documents_parent", "documents", ["parent_document_id"])

    # Dedupe applies to uploads, not to the packets split out of one (see docstring).
    op.drop_index(_DEDUPE_INDEX, table_name="documents")
    op.create_index(
        _DEDUPE_INDEX,
        "documents",
        ["tenant_id", "content_hash"],
        unique=True,
        postgresql_where=sa.text("parent_document_id IS NULL"),
    )


def downgrade() -> None:
    # Restoring the total unique index fails if any child rows exist, which is correct:
    # silently dropping them would lose documents. Delete children first, deliberately.
    op.drop_index(_DEDUPE_INDEX, table_name="documents")
    op.create_index(_DEDUPE_INDEX, "documents", ["tenant_id", "content_hash"], unique=True)
    op.drop_index("ix_documents_parent", table_name="documents")
    op.drop_constraint("fk_documents_parent_document_id", "documents", type_="foreignkey")
    op.drop_column("documents", "packet_index")
    op.drop_column("documents", "parent_document_id")
