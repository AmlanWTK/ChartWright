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

import uuid
from dataclasses import dataclass

from chartwright_db import DocumentRepository, build_engine, tenant_context
from chartwright_events import EventPublisher, publisher_from_env
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

    def __init__(self, publisher: EventPublisher | None = None):
        self._engine = build_engine()
        self._publisher = publisher or publisher_from_env()

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

            repo.transition_status(doc_id, input.to_status)
            return input.to_status

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
