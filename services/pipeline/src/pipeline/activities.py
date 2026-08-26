"""Temporal activities: idempotent stage transitions against the CP08 persistence layer.

Idempotency contract (ADR-0001): activities may be retried or re-delivered; re-running a
transition the document has already passed is a no-op, not an error. The status ORDER
below defines "already passed". Every real transition is audited by the repository.

Stage stubs: in CP10 each stage only advances the state machine. Later checkpoints
replace stage bodies with real work (CP13 preprocess, CP14 classify, ...) WITHOUT
changing the workflow shape — that is the point of building the skeleton first.

Poison hook (for chaos/DLQ testing): a document whose external_ref is
``poison:<STATUS>`` fails deterministically when that stage runs, exhausting retries and
exercising the FAILED + DLQ path end-to-end.
"""

from __future__ import annotations

import io
import uuid
from dataclasses import dataclass

from chartwright_classify import classify_packet
from chartwright_db import (
    Document,
    DocumentRepository,
    NormalizedPageInput,
    build_engine,
    tenant_context,
)
from chartwright_events import EventPublisher, publisher_from_env
from chartwright_gateway import ModelGateway, build_default_gateway
from chartwright_preprocess import (
    HeuristicSplitter,
    file_type_from_extension,
    load_pages,
    normalize_page,
)
from chartwright_storage import ObjectStorage
from PIL import Image
from pipeline.config import PipelineSettings, get_pipeline_settings
from temporalio import activity

# Lifecycle order — used to decide "already past this stage" for idempotent re-runs.
STATUS_ORDER: list[str] = [
    "RECEIVED",
    "NORMALIZED",
    "CLASSIFIED",
    "OCR_DONE",
    "EXTRACTED",
    "VALIDATED_FIELDS",
    "POLICY_CHECKED",
    "PACKET_ASSEMBLED",
    "OUTPUT_EMITTED",
    "COMPLETED",
]

PIPELINE_STAGES: list[str] = STATUS_ORDER[1:]  # everything after RECEIVED


@dataclass
class StageInput:
    document_id: str
    tenant_id: str
    to_status: str


@dataclass
class FailInput:
    document_id: str
    tenant_id: str
    reason: str


class PoisonedDocumentError(Exception):
    """Deterministic failure injected via the poison hook (testing/chaos)."""


class PipelineActivities:
    """Activity implementations bound to a DB engine + event publisher."""

    def __init__(
        self,
        publisher: EventPublisher | None = None,
        *,
        storage: ObjectStorage | None = None,
        settings: PipelineSettings | None = None,
        gateway: ModelGateway | None = None,
    ):
        self._engine = build_engine()
        self._publisher = publisher or publisher_from_env()
        self._settings = settings or get_pipeline_settings()
        self._storage = storage or ObjectStorage(self._settings)
        self._gateway = gateway or build_default_gateway()

    @activity.defn
    def advance_stage(self, input: StageInput) -> str:
        """Advance the document to ``to_status``; no-op if already at/past it."""
        doc_id = uuid.UUID(input.document_id)
        tenant_id = uuid.UUID(input.tenant_id)
        with tenant_context(self._engine, tenant_id) as session:
            repo = DocumentRepository(session, actor="pipeline-worker")
            doc = repo.get(doc_id)
            if doc is None:
                msg = f"document {doc_id} not found for tenant {tenant_id}"
                raise RuntimeError(msg)

            # Poison hook: deterministic failure for DLQ/chaos testing.
            if doc.external_ref == f"poison:{input.to_status}":
                msg = f"poisoned at stage {input.to_status} (test hook)"
                raise PoisonedDocumentError(msg)

            current_idx = STATUS_ORDER.index(doc.status) if doc.status in STATUS_ORDER else -1
            target_idx = STATUS_ORDER.index(input.to_status)
            if current_idx >= target_idx:
                return doc.status  # idempotent re-run: already there or past it

            if input.to_status == "NORMALIZED":
                self._normalize_document(repo, tenant_id, doc)
            elif input.to_status == "CLASSIFIED":
                self._classify_document(repo, tenant_id, doc)

            repo.transition_status(doc_id, input.to_status)
            return input.to_status

    def _normalize_document(
        self, repo: DocumentRepository, tenant_id: uuid.UUID, doc: Document
    ) -> None:
        """CP13: rasterize the stored original, correct page geometry, split into
        packets, and persist both — all pixel-only, no model calls (see
        chartwright_preprocess). Structural-signal packet splitting is deliberate:
        neither classification (CP14) nor OCR (CP12) has run yet at this point in
        STATUS_ORDER, so this is the earliest stage that *can* split reliably.
        """
        original_key = doc.original_object_key
        if original_key is None:
            msg = f"document {doc.id} has no original_object_key; cannot normalize"
            raise RuntimeError(msg)

        extension = "." + original_key.rsplit(".", 1)[-1]
        file_type = file_type_from_extension(extension)
        data = self._storage.get(original_key)
        pages = load_pages(data, file_type)
        # Computed once and reused below for both storage and splitting — normalize_page's
        # skew search is the expensive part of this stage; never run it twice per page.
        normalized_pages = [normalize_page(page) for page in pages]

        page_inputs: list[NormalizedPageInput] = []
        for i, normalized in enumerate(normalized_pages, start=1):
            buf = io.BytesIO()
            normalized.image.save(buf, format="PNG")
            key = self._storage.put_normalized_page(
                tenant_id=tenant_id, document_id=doc.id, page_number=i, data=buf.getvalue()
            )
            page_inputs.append(
                NormalizedPageInput(
                    page_number=i,
                    width=normalized.image.width,
                    height=normalized.image.height,
                    image_object_key=key,
                )
            )

        manifest_key = f"tenants/{tenant_id}/documents/{doc.id}/normalized/"
        repo.record_normalized_pages(doc.id, page_inputs, normalized_object_key=manifest_key)

        packets = HeuristicSplitter().split([p.image for p in normalized_pages])
        repo.record_packet_split(
            doc.id,
            packet_count=len(packets),
            boundaries=[list(p.page_indices) for p in packets],
        )

    def _classify_document(
        self, repo: DocumentRepository, tenant_id: uuid.UUID, doc: Document
    ) -> None:
        """CP14: classify from the document's first normalized page only (approved
        scope — see docs/CP14-document-classification.md). Packet splitting (CP13)
        partitions contiguously from page index 0, so the document's first normalized
        page is always the first page of its first packet; no need to re-read CP13's
        packet-split audit entry just to find it.

        First model call in the pipeline (CP12/CP13 are both deterministic). The model
        describes the page in free text and chartwright_classify maps that description
        onto a DocType in deterministic code (ADR-0010); confidence is derived from how
        unambiguous the description was, and is explicitly UNCALIBRATED — see that
        library's README. Never raises on a malformed model response
        (classify_packet's own OTHER-fallback handles that); a missing first page,
        however, is a real bug (NORMALIZED must have already produced one) and does
        raise, same discipline as _normalize_document's original_object_key guard.
        """
        first_page = repo.get_page(doc.id, 1)
        if first_page is None or first_page.image_object_key is None:
            msg = f"document {doc.id} has no normalized first page; cannot classify"
            raise RuntimeError(msg)

        data = self._storage.get(first_page.image_object_key)
        image = Image.open(io.BytesIO(data)).convert("RGB")
        result = classify_packet(image, gateway=self._gateway, tenant_id=str(tenant_id))
        repo.record_classification(
            doc.id, doc_type=result.doc_type.value, confidence=result.confidence
        )

    @activity.defn
    def mark_failed(self, input: FailInput) -> None:
        """Terminal failure: set FAILED (audited) and publish a DLQ event for replay."""
        doc_id = uuid.UUID(input.document_id)
        tenant_id = uuid.UUID(input.tenant_id)
        with tenant_context(self._engine, tenant_id) as session:
            DocumentRepository(session, actor="pipeline-worker").transition_status(doc_id, "FAILED")
        self._publisher.publish(
            "document.dlq",
            {
                "document_id": input.document_id,
                "tenant_id": input.tenant_id,
                "reason": input.reason,  # structured reason; no PHI
            },
        )
