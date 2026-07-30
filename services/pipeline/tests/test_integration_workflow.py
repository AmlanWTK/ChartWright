"""Integration tests — CP10 acceptance. Requires local stack (Temporal + Postgres).

Proves against a real Temporal server:
1. Full lifecycle: RECEIVED -> ... -> COMPLETED, every transition audited.
2. Poison stage -> retries exhaust -> FAILED (+ DLQ event) — no document lost.
3. Workflow-ID dedupe: the same document cannot start twice (exactly-once effect
   under at-least-once event delivery).
4. Replay: a FAILED document re-runs cleanly once the cause is fixed (idempotent stages).

The worker runs IN-PROCESS on a unique task queue per test run, so tests are
self-contained and don't collide with a separately running `python -m pipeline.worker`.
"""

import uuid

import pytest
from chartwright_db import (
    AuditLog,
    DocumentRepository,
    Tenant,
    admin_database_url,
    build_engine,
    no_tenant_session,
    tenant_context,
)
from chartwright_events import LoggingEventPublisher
from pipeline.activities import PipelineActivities
from pipeline.workflows import DocumentPipelineWorkflow, PipelineInput
from sqlalchemy import select, text
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError
from temporalio.worker import Worker

pytestmark = pytest.mark.integration

TASK_QUEUE = f"cp10-test-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def db():  # type: ignore[no-untyped-def]
    admin = build_engine(admin_database_url())
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover
        pytest.skip("Postgres not reachable (make local-up + db-upgrade)")
    tenant_id = uuid.uuid4()
    with no_tenant_session(admin) as s:
        s.add(Tenant(id=tenant_id, name=f"cp10-test-{tenant_id.hex[:8]}"))
    return build_engine(), tenant_id


@pytest.fixture()
async def temporal_client():  # type: ignore[no-untyped-def]
    try:
        return await Client.connect("localhost:7233")
    except Exception:  # pragma: no cover
        pytest.skip("Temporal not reachable (make local-up)")


def _make_received_doc(engine, tenant_id: uuid.UUID, external_ref: str | None = None) -> str:  # type: ignore[no-untyped-def]
    with tenant_context(engine, tenant_id) as s:
        doc = DocumentRepository(s, actor="cp10-test").create_document(
            source_channel="api", content_hash=uuid.uuid4().hex, external_ref=external_ref
        )
        return str(doc.id)


def _worker(client: Client) -> Worker:
    from concurrent.futures import ThreadPoolExecutor

    activities = PipelineActivities(publisher=LoggingEventPublisher())
    return Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DocumentPipelineWorkflow],
        activities=[activities.advance_stage, activities.mark_failed],
        activity_executor=ThreadPoolExecutor(max_workers=4),
    )


class TestLifecycle:
    async def test_document_reaches_completed_with_full_audit_trail(
        self, db, temporal_client
    ) -> None:  # type: ignore[no-untyped-def]
        engine, tenant_id = db
        doc_id = _make_received_doc(engine, tenant_id)
        async with _worker(temporal_client):
            result = await temporal_client.execute_workflow(
                DocumentPipelineWorkflow.run,
                PipelineInput(document_id=doc_id, tenant_id=str(tenant_id)),
                id=f"doc-{doc_id}",
                task_queue=TASK_QUEUE,
            )
        assert result.final_status == "COMPLETED"
        with tenant_context(engine, tenant_id) as s:
            doc = DocumentRepository(s, actor="cp10-test").get(uuid.UUID(doc_id))
            assert doc is not None and doc.status == "COMPLETED"
            transitions = list(
                s.execute(
                    select(AuditLog).where(
                        AuditLog.entity_id == uuid.UUID(doc_id),
                        AuditLog.action == "status_change",
                    )
                ).scalars()
            )
            # RECEIVED -> 9 subsequent stages, each audited exactly once.
            assert len(transitions) == 9

    async def test_poisoned_stage_lands_in_failed_not_lost(self, db, temporal_client) -> None:  # type: ignore[no-untyped-def]
        engine, tenant_id = db
        doc_id = _make_received_doc(engine, tenant_id, external_ref="poison:CLASSIFIED")
        async with _worker(temporal_client):
            result = await temporal_client.execute_workflow(
                DocumentPipelineWorkflow.run,
                PipelineInput(document_id=doc_id, tenant_id=str(tenant_id), max_attempts=2),
                id=f"doc-{doc_id}",
                task_queue=TASK_QUEUE,
            )
        assert result.final_status == "FAILED"
        assert result.failed_stage == "CLASSIFIED"
        with tenant_context(engine, tenant_id) as s:
            doc = DocumentRepository(s, actor="cp10-test").get(uuid.UUID(doc_id))
            assert doc is not None and doc.status == "FAILED"


class TestExactlyOnceStart:
    async def test_same_document_cannot_start_twice(self, db, temporal_client) -> None:  # type: ignore[no-untyped-def]
        """The dedupe that makes at-least-once Kafka delivery safe."""
        engine, tenant_id = db
        doc_id = _make_received_doc(engine, tenant_id)
        async with _worker(temporal_client):
            handle = await temporal_client.start_workflow(
                DocumentPipelineWorkflow.run,
                PipelineInput(document_id=doc_id, tenant_id=str(tenant_id)),
                id=f"doc-{doc_id}",
                task_queue=TASK_QUEUE,
            )
            with pytest.raises(WorkflowAlreadyStartedError):
                await temporal_client.start_workflow(
                    DocumentPipelineWorkflow.run,
                    PipelineInput(document_id=doc_id, tenant_id=str(tenant_id)),
                    id=f"doc-{doc_id}",
                    task_queue=TASK_QUEUE,
                )
            await handle.result()


class TestReplay:
    async def test_failed_document_replays_to_completed(self, db, temporal_client) -> None:  # type: ignore[no-untyped-def]
        """DLQ recovery: fix the cause (clear the poison), replay, reach COMPLETED."""
        engine, tenant_id = db
        doc_id = _make_received_doc(engine, tenant_id, external_ref="poison:OCR_DONE")
        async with _worker(temporal_client):
            first = await temporal_client.execute_workflow(
                DocumentPipelineWorkflow.run,
                PipelineInput(document_id=doc_id, tenant_id=str(tenant_id), max_attempts=2),
                id=f"doc-{doc_id}",
                task_queue=TASK_QUEUE,
            )
            assert first.final_status == "FAILED"
            # Operator fixes the cause:
            with tenant_context(engine, tenant_id) as s:
                doc = DocumentRepository(s, actor="cp10-test").get(uuid.UUID(doc_id))
                assert doc is not None
                doc.external_ref = None
            # Replay under a new run id (mirrors scripts/replay_document.py):
            second = await temporal_client.execute_workflow(
                DocumentPipelineWorkflow.run,
                PipelineInput(document_id=doc_id, tenant_id=str(tenant_id)),
                id=f"doc-{doc_id}-replay-test",
                task_queue=TASK_QUEUE,
            )
            assert second.final_status == "COMPLETED"
