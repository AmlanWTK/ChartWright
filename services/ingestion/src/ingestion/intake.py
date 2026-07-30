"""The intake pipeline: validate -> scan -> hash -> dedupe -> store -> record -> emit.

Ordering rationale:
- Validate + scan BEFORE storing to the accepted-documents prefix (never persist
  unvetted bytes where processing can reach them).
- Dedupe by sha256 content hash inside the tenant (FR-ING-04): resubmission returns
  the same document, no duplicate storage or events beyond a dedupe-flagged RECEIVED.
- Infected files ARE recorded (status QUARANTINED, bytes under quarantine/) so there
  is an auditable trail of the attempt, but they never enter the processing pipeline.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass

from chartwright_db import DocumentRepository, tenant_context
from sqlalchemy import Engine

from ingestion.config import Settings
from ingestion.events import EventPublisher, document_received_event
from ingestion.scanner import Scanner, ScanVerdict
from ingestion.storage import ObjectStorage
from ingestion.validation import detect_file_type, extension_for, validate_size


@dataclass(frozen=True)
class IntakeResult:
    document_id: uuid.UUID
    status: str  # RECEIVED | QUARANTINED
    dedupe: bool
    file_type: str


class IntakeService:
    def __init__(
        self,
        *,
        engine: Engine,
        storage: ObjectStorage,
        scanner: Scanner,
        events: EventPublisher,
        settings: Settings,
    ):
        self._engine = engine
        self._storage = storage
        self._scanner = scanner
        self._events = events
        self._settings = settings

    @property
    def engine(self) -> Engine:
        """Shared engine for request-scoped tenant sessions at the API layer."""
        return self._engine

    def submit(
        self,
        *,
        tenant_id: uuid.UUID,
        data: bytes,
        source_channel: str,
        external_ref: str | None = None,
        actor: str = "ingestion-api",
    ) -> IntakeResult:
        # 1) Deterministic validation (raises ValidationError -> 422 at the API layer).
        validate_size(data, self._settings.max_upload_bytes)
        ftype = detect_file_type(data)
        extension = extension_for(ftype)

        # 2) Malware scan before anything is persisted to the accepted prefix.
        verdict, threat = self._scanner.scan(data)
        content_hash = hashlib.sha256(data).hexdigest()

        if verdict == ScanVerdict.INFECTED:
            with tenant_context(self._engine, tenant_id) as session:
                repo = DocumentRepository(session, actor=actor)
                doc = repo.create_document(
                    source_channel=source_channel,
                    content_hash=content_hash,
                    external_ref=external_ref,
                )
                key = self._storage.put_quarantined(
                    tenant_id=tenant_id, document_id=doc.id, data=data, extension=extension
                )
                doc.original_object_key = key
                repo.transition_status(doc.id, "QUARANTINED")
                doc_id = doc.id
            # Quarantine is recorded + audited; NO received event (never enters pipeline).
            _ = threat  # threat name is in the audit trail via status change context
            return IntakeResult(
                document_id=doc_id, status="QUARANTINED", dedupe=False, file_type=ftype.value
            )

        # 3) Clean path: dedupe-or-create, store original, emit RECEIVED.
        with tenant_context(self._engine, tenant_id) as session:
            repo = DocumentRepository(session, actor=actor)
            doc = repo.create_document(
                source_channel=source_channel,
                content_hash=content_hash,
                external_ref=external_ref,
            )
            dedupe = doc.original_object_key is not None  # existed with stored bytes already
            if not dedupe:
                key = self._storage.put_original(
                    tenant_id=tenant_id, document_id=doc.id, data=data, extension=extension
                )
                doc.original_object_key = key
            doc_id, status = doc.id, doc.status

        event_type, payload = document_received_event(
            tenant_id=tenant_id, document_id=doc_id, source_channel=source_channel, dedupe=dedupe
        )
        self._events.publish(event_type, payload)
        return IntakeResult(document_id=doc_id, status=status, dedupe=dedupe, file_type=ftype.value)
