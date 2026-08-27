"""Repositories: the only way services touch tenant data. Audit-on-write built in.

Every mutating method records an ``audit_log`` row in the same session/transaction —
if the change commits, its audit trail commits with it (and vice versa).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from chartwright_db.models import (
    AuditLog,
    Document,
    DocumentPage,
    ExtractedField,
    Extraction,
    ReviewTask,
)


@dataclass(frozen=True)
class NormalizedPageInput:
    """One CP13-normalized page, ready to persist — mirrors the DocumentPage columns
    that stage actually populates (quality_score/model_tier_used are set later, by the
    routing logic those columns already exist for)."""

    page_number: int
    width: int
    height: int
    image_object_key: str


def _snapshot(obj: object, keys: tuple[str, ...]) -> dict[str, Any]:
    return {k: _jsonable(getattr(obj, k)) for k in keys}


def _jsonable(v: object) -> object:
    return str(v) if isinstance(v, uuid.UUID) else v


class _AuditedRepository:
    """Base: holds the session, the acting principal, and the audit writer."""

    def __init__(self, session: Session, *, actor: str, correlation_id: str | None = None):
        self.session = session
        self.actor = actor
        self.correlation_id = correlation_id

    def _tenant_id(self) -> uuid.UUID:
        """The tenant bound to this transaction (set by tenant_context)."""
        from sqlalchemy import text

        value = self.session.execute(
            text("SELECT current_setting('app.current_tenant', true)")
        ).scalar_one()
        if not value:
            msg = "No tenant context: repositories must run inside tenant_context()."
            raise RuntimeError(msg)
        return uuid.UUID(value)

    def _audit(
        self,
        action: str,
        entity_type: str,
        entity_id: uuid.UUID,
        *,
        before: dict[str, Any] | None = None,
        after: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                tenant_id=self._tenant_id(),
                actor=self.actor,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                before=before,
                after=after,
                correlation_id=self.correlation_id,
            )
        )


class DocumentRepository(_AuditedRepository):
    _DOC_SNAPSHOT = ("status", "doc_type", "page_count", "content_hash")

    def create_document(
        self,
        *,
        source_channel: str,
        content_hash: str,
        page_count: int = 0,
        external_ref: str | None = None,
        original_object_key: str | None = None,
    ) -> Document:
        """Create a document, or return the existing one with the same content hash
        (idempotent ingestion — FR-ING-04).

        Scoped to uploads (``parent_document_id IS NULL``) since CP15's packet fan-out:
        a mixed upload's children all carry the parent's content_hash, so an unscoped
        lookup would match parent + N children and ``scalar_one_or_none`` would raise
        MultipleResultsFound — i.e. resubmitting a multi-packet fax would crash intake.
        The same predicate keys the partial unique index added in migration 0003, so the
        query and the constraint agree on what "already ingested" means.
        """
        existing = self.session.execute(
            select(Document).where(
                Document.content_hash == content_hash,
                Document.parent_document_id.is_(None),
            )
        ).scalar_one_or_none()
        if existing is not None:
            return existing

        doc = Document(
            tenant_id=self._tenant_id(),
            source_channel=source_channel,
            content_hash=content_hash,
            page_count=page_count,
            external_ref=external_ref,
            original_object_key=original_object_key,
        )
        self.session.add(doc)
        self.session.flush()  # assign PK for the audit row
        self._audit("create", "document", doc.id, after=_snapshot(doc, self._DOC_SNAPSHOT))
        return doc

    def transition_status(self, document_id: uuid.UUID, new_status: str) -> Document:
        doc = self.session.get_one(Document, document_id)
        before = _snapshot(doc, self._DOC_SNAPSHOT)
        doc.status = new_status
        self.session.flush()
        self._audit(
            "status_change",
            "document",
            doc.id,
            before=before,
            after=_snapshot(doc, self._DOC_SNAPSHOT),
        )
        return doc

    def get(self, document_id: uuid.UUID) -> Document | None:
        return self.session.get(Document, document_id)

    def record_normalized_pages(
        self,
        document_id: uuid.UUID,
        pages: list[NormalizedPageInput],
        *,
        normalized_object_key: str,
    ) -> Document:
        """CP13: persist normalized page rows and point the document at the manifest.
        Idempotent re-run safe: an existing (document_id, page_number) row is updated in
        place rather than duplicated, per the unique index on that pair."""
        doc = self.session.get_one(Document, document_id)
        before = _snapshot(doc, self._DOC_SNAPSHOT)

        existing = {
            p.page_number: p
            for p in self.session.execute(
                select(DocumentPage).where(DocumentPage.document_id == document_id)
            ).scalars()
        }
        for page in pages:
            row = existing.get(page.page_number)
            if row is None:
                self.session.add(
                    DocumentPage(
                        tenant_id=self._tenant_id(),
                        document_id=document_id,
                        page_number=page.page_number,
                        width=page.width,
                        height=page.height,
                        image_object_key=page.image_object_key,
                    )
                )
            else:
                row.width = page.width
                row.height = page.height
                row.image_object_key = page.image_object_key

        doc.normalized_object_key = normalized_object_key
        doc.page_count = len(pages)
        self.session.flush()
        self._audit(
            "normalize",
            "document",
            doc.id,
            before=before,
            after=_snapshot(doc, self._DOC_SNAPSHOT),
        )
        return doc

    def record_packet_split(
        self,
        document_id: uuid.UUID,
        *,
        packet_count: int,
        boundaries: list[list[int]],
    ) -> None:
        """CP13: audit-log the structural packet split. No schema change — the packet
        table lands with CP14/CP15 once classification exists to assign a doc_type per
        packet (see docs/CP13-preprocessing-packet-splitting.md, "deferred to a later
        checkpoint"); until then this is the split's system of record."""
        self._audit(
            "packet_split",
            "document",
            document_id,
            after={"packet_count": packet_count, "boundaries": boundaries},
        )

    def create_child_document(
        self, parent: Document, *, packet_index: int, page_count: int
    ) -> Document:
        """Create one packet child of ``parent``, routed independently from CLASSIFIED on.

        CP13 splits an upload into logical packets; extraction (CP15) is per document type,
        so each packet needs its own Document row rather than sharing the parent's.

        The child deliberately reuses the parent's ``content_hash`` and
        ``original_object_key``: it is the same uploaded bytes, and pretending otherwise
        would break provenance. That is only legal because migration 0003 made the dedupe
        index PARTIAL (``WHERE parent_document_id IS NULL``) -- a total unique index on
        (tenant_id, content_hash) would reject every child after the first.

        Starts at NORMALIZED, not RECEIVED: the parent already did intake and page
        normalization, and re-running those per packet would duplicate work and pages.
        """
        child = Document(
            tenant_id=self._tenant_id(),
            parent_document_id=parent.id,
            packet_index=packet_index,
            external_ref=parent.external_ref,
            source_channel=parent.source_channel,
            content_hash=parent.content_hash,
            page_count=page_count,
            original_object_key=parent.original_object_key,
            status="NORMALIZED",
        )
        self.session.add(child)
        self.session.flush()
        self._audit(
            "create",
            "document",
            child.id,
            after={
                "parent_document_id": str(parent.id),
                "packet_index": packet_index,
                "page_count": page_count,
                "status": "NORMALIZED",
            },
        )
        return child

    def list_children(self, parent_id: uuid.UUID) -> list[Document]:
        """Packet children of an upload, in packet order (empty for a single-packet doc)."""
        stmt = (
            select(Document)
            .where(Document.parent_document_id == parent_id)
            .order_by(Document.packet_index)
        )
        return list(self.session.scalars(stmt))

    def get_page(self, document_id: uuid.UUID, page_number: int) -> DocumentPage | None:
        return self.session.execute(
            select(DocumentPage).where(
                DocumentPage.document_id == document_id, DocumentPage.page_number == page_number
            )
        ).scalar_one_or_none()

    def record_classification(
        self,
        document_id: uuid.UUID,
        *,
        doc_type: str,
        confidence: float,
    ) -> Document:
        """CP14: persist the classifier's verdict. ``confidence`` is the model's
        self-report — stored as-is but UNCALIBRATED (see chartwright_classify's README);
        do not use it for routing decisions before CP17. Idempotent re-run safe: setting
        the same fields again is a no-op transition-wise, just re-audited."""
        doc = self.session.get_one(Document, document_id)
        before = _snapshot(doc, self._DOC_SNAPSHOT)
        doc.doc_type = doc_type
        doc.doc_type_confidence = confidence
        self.session.flush()
        self._audit(
            "classify",
            "document",
            doc.id,
            before=before,
            after=_snapshot(doc, self._DOC_SNAPSHOT),
        )
        return doc

    def list_by_status(self, status: str, *, limit: int = 100) -> list[Document]:
        return list(
            self.session.execute(
                select(Document).where(Document.status == status).limit(limit)
            ).scalars()
        )


class ExtractionRepository(_AuditedRepository):
    def create_extraction(
        self,
        *,
        document_id: uuid.UUID,
        doc_type: str,
        schema_version: str,
        overall_confidence: float | None = None,
    ) -> Extraction:
        ext = Extraction(
            tenant_id=self._tenant_id(),
            document_id=document_id,
            doc_type=doc_type,
            schema_version=schema_version,
            overall_confidence=overall_confidence,
        )
        self.session.add(ext)
        self.session.flush()
        self._audit(
            "create",
            "extraction",
            ext.id,
            after={"document_id": str(document_id), "doc_type": doc_type},
        )
        return ext

    def add_field(
        self,
        *,
        extraction_id: uuid.UUID,
        field_key: str,
        value_raw: str,
        confidence: float,
        page_number: int,
        bbox: dict[str, float],
        source_span: str,
        tier: int = 0,
        needs_review: bool = False,
    ) -> ExtractedField:
        field = ExtractedField(
            tenant_id=self._tenant_id(),
            extraction_id=extraction_id,
            field_key=field_key,
            value_raw=value_raw,
            confidence=confidence,
            page_number=page_number,
            bbox=bbox,
            source_span=source_span,
            tier=tier,
            needs_review=needs_review,
        )
        self.session.add(field)
        self.session.flush()
        # Note: field creation is audited at extraction granularity to bound audit volume;
        # reviewer *corrections* (the consequential change) are audited per field below.
        return field

    def record_review(
        self,
        field_id: uuid.UUID,
        *,
        action: str,  # accept|edit|reject
        corrected_value: str | None = None,
        reviewer_id: uuid.UUID | None = None,
    ) -> ExtractedField:
        field = self.session.get_one(ExtractedField, field_id)
        before = {"value_raw": field.value_raw, "review_action": field.review_action}
        field.review_action = action
        field.corrected_value = corrected_value
        field.reviewed_by = reviewer_id
        field.needs_review = False
        self.session.flush()
        self._audit(
            "review",
            "extracted_field",
            field.id,
            before=before,
            after={"review_action": action, "corrected_value": corrected_value},
        )
        return field


class ReviewTaskRepository(_AuditedRepository):
    def open_task(
        self,
        *,
        document_id: uuid.UUID,
        reason: str,
        priority: int = 100,
    ) -> ReviewTask:
        task = ReviewTask(
            tenant_id=self._tenant_id(),
            document_id=document_id,
            reason=reason,
            priority=priority,
        )
        self.session.add(task)
        self.session.flush()
        self._audit("create", "review_task", task.id, after={"reason": reason})
        return task

    def next_open(self, *, limit: int = 20) -> list[ReviewTask]:
        return list(
            self.session.execute(
                select(ReviewTask)
                .where(ReviewTask.status == "open")
                .order_by(ReviewTask.priority, ReviewTask.opened_at)
                .limit(limit)
            ).scalars()
        )
