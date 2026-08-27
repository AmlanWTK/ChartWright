"""SQLAlchemy 2.0 typed models — the relational spine (CP08).

Design rules (from `10-database-design.md`):
- Every tenant-owned table carries ``tenant_id`` and is protected by RLS (see migration 0001).
- Provenance (page/bbox/span/confidence) is first-class on extracted fields — the grounding
  contract (ADR-0003) made physical.
- ``audit_log`` is append-only; it is written, never updated or deleted.
- Timestamps are UTC. JSONB holds the flexible parts (bboxes, cells, snapshots).

Deliberately NOT here yet (no building ahead): policy tables (CP18), agent_runs (CP20),
outputs (CP22), eval tables (CP26).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(tz=UTC)


class Base(DeclarativeBase):
    type_annotation_map = {  # noqa: RUF012 - SQLAlchemy declarative config attribute
        dict[str, Any]: JSONB,
        uuid.UUID: UUID(as_uuid=True),
    }


# --------------------------------------------------------------------------------------
# Tenancy & identity
# --------------------------------------------------------------------------------------


class Tenant(Base):
    """An organization. NOT itself RLS-protected (it is the isolation root)."""

    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), unique=True)
    tier: Mapped[str] = mapped_column(String(50), default="standard")
    retention_days: Mapped[int] = mapped_column(Integer, default=2555)  # ~7y healthcare default
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(320))
    role: Mapped[str] = mapped_column(String(50), default="reviewer")
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    __table_args__ = (Index("ix_users_tenant_email", "tenant_id", "email", unique=True),)


# --------------------------------------------------------------------------------------
# Document lifecycle
# --------------------------------------------------------------------------------------


class Document(Base):
    """One logical document moving through the state machine (`08-system-architecture.md`)."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    external_ref: Mapped[str | None] = mapped_column(String(200))
    source_channel: Mapped[str] = mapped_column(String(20))  # api|fax|sftp|email
    content_hash: Mapped[str] = mapped_column(String(64))  # sha256 hex; dedupe key
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    doc_type: Mapped[str | None] = mapped_column(String(50))  # DocType value once classified
    doc_type_confidence: Mapped[float | None] = mapped_column(Float)
    status: Mapped[str] = mapped_column(String(30), default="RECEIVED", index=True)
    original_object_key: Mapped[str | None] = mapped_column(String(500))
    normalized_object_key: Mapped[str | None] = mapped_column(String(500))
    # Packet fan-out (CP15): NULL parent means "this row IS the upload". A child is one
    # packet split out of its parent by CP13, routed independently from CLASSIFIED on.
    parent_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True
    )
    packet_index: Mapped[int | None] = mapped_column(Integer)  # 1-based within parent
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    pages: Mapped[list[DocumentPage]] = relationship(back_populates="document")
    extractions: Mapped[list[Extraction]] = relationship(back_populates="document")

    __table_args__ = (
        # Dedupe: the same content submitted twice by a tenant maps to one document.
        # PARTIAL on purpose (migration 0003): every packet child shares its parent's
        # content_hash -- same bytes -- so a total unique index would reject the fan-out.
        # Dedupe is a property of uploads, not of the packets split out of one.
        Index(
            "ix_documents_tenant_hash",
            "tenant_id",
            "content_hash",
            unique=True,
            postgresql_where=text("parent_document_id IS NULL"),
        ),
        Index("ix_documents_tenant_status_sla", "tenant_id", "status", "sla_due_at"),
    )


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)  # 1-based
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    image_object_key: Mapped[str | None] = mapped_column(String(500))
    quality_score: Mapped[float | None] = mapped_column(Float)  # feeds the router (CP13/CP17)
    model_tier_used: Mapped[int | None] = mapped_column(Integer)  # 0/1/2; cost attribution

    document: Mapped[Document] = relationship(back_populates="pages")

    __table_args__ = (Index("ix_pages_document_number", "document_id", "page_number", unique=True),)


# --------------------------------------------------------------------------------------
# Grounded extraction
# --------------------------------------------------------------------------------------


class Extraction(Base):
    """One extraction run over a document (re-runs create new rows; history preserved)."""

    __tablename__ = "extractions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    schema_version: Mapped[str] = mapped_column(String(20))
    doc_type: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30), default="EXTRACTED")
    overall_confidence: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped[Document] = relationship(back_populates="extractions")
    fields: Mapped[list[ExtractedField]] = relationship(back_populates="extraction")
    tables: Mapped[list[ExtractedTable]] = relationship(back_populates="extraction")


class ExtractedField(Base):
    """A grounded field — the ADR-0003 contract as columns."""

    __tablename__ = "extracted_fields"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extractions.id"), index=True)
    field_key: Mapped[str] = mapped_column(String(100))
    value_raw: Mapped[str] = mapped_column(Text)
    value_normalized: Mapped[str | None] = mapped_column(Text)
    code_system: Mapped[str | None] = mapped_column(String(20))
    confidence: Mapped[float] = mapped_column(Float)
    page_number: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[dict[str, Any]] = mapped_column(JSONB)  # {x,y,w,h}
    source_span: Mapped[str] = mapped_column(Text)
    tier: Mapped[int] = mapped_column(Integer, default=0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    review_action: Mapped[str | None] = mapped_column(String(20))  # accept|edit|reject
    corrected_value: Mapped[str | None] = mapped_column(Text)  # label capture (flywheel)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    extraction: Mapped[Extraction] = relationship(back_populates="fields")

    __table_args__ = (
        Index(
            "ix_fields_needs_review",
            "tenant_id",
            "needs_review",
            postgresql_where=(needs_review.is_(True)),  # partial index for the hot queue
        ),
    )


class ExtractedTable(Base):
    __tablename__ = "extracted_tables"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    extraction_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("extractions.id"), index=True)
    table_key: Mapped[str] = mapped_column(String(100))
    page_number: Mapped[int] = mapped_column(Integer)
    bbox: Mapped[dict[str, Any]] = mapped_column(JSONB)
    cells: Mapped[dict[str, Any]] = mapped_column(JSONB)  # {"cells": [{r,c,text,conf,bbox}]}
    confidence: Mapped[float] = mapped_column(Float)

    extraction: Mapped[Extraction] = relationship(back_populates="tables")


# --------------------------------------------------------------------------------------
# Review queue & audit
# --------------------------------------------------------------------------------------


class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id"), index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100)  # lower = more urgent
    reason: Mapped[str] = mapped_column(String(100))  # low_confidence|always_review|...
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (
        Index(
            "ix_review_open_queue",
            "tenant_id",
            "priority",
            "sla_due_at",
            postgresql_where=(status == "open"),
        ),
    )


class AuditLog(Base):
    """Append-only. Written in the same transaction as the change it records.

    Never updated, never deleted by the application; retention is a governed archival
    process, not a DELETE. (Enforced socially now; a DB rule lands with hardening.)
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tenants.id"), index=True)
    actor: Mapped[str] = mapped_column(String(200))  # user id or service name
    action: Mapped[str] = mapped_column(String(50))  # create|update|status_change|...
    entity_type: Mapped[str] = mapped_column(String(50))
    entity_id: Mapped[uuid.UUID] = mapped_column()
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    correlation_id: Mapped[str | None] = mapped_column(String(100))
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )


# Tables under RLS (everything tenant-owned; `tenants` itself is not).
RLS_TABLES: tuple[str, ...] = (
    "users",
    "documents",
    "document_pages",
    "extractions",
    "extracted_fields",
    "extracted_tables",
    "review_tasks",
    "audit_log",
)
