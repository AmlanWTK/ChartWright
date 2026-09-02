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

import io
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
from chartwright_preprocess import load_pages
from chartwright_storage import ObjectStorage
from chartwright_synthdata import generate_prior_auth
from chartwright_synthdata.classify_docs import generate_insurance_card
from PIL import Image, ImageDraw
from pipeline.activities import PipelineActivities
from pipeline.config import get_pipeline_settings
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


def _object_storage() -> ObjectStorage:
    # Same s3_* defaults as ingestion.config.Settings — same CP04-L MinIO container.
    return ObjectStorage(get_pipeline_settings())


def _make_received_doc(engine, tenant_id: uuid.UUID, external_ref: str | None = None) -> str:  # type: ignore[no-untyped-def]
    """A RECEIVED document with a real stored original — CP13's NORMALIZED stage now
    does real work (rasterize + normalize + split), so every fixture document needs an
    actual object in storage, exactly like CP09 ingestion always provides in production.
    """
    storage = _object_storage()
    with tenant_context(engine, tenant_id) as s:
        repo = DocumentRepository(s, actor="cp10-test")
        doc = repo.create_document(
            source_channel="api", content_hash=uuid.uuid4().hex, external_ref=external_ref
        )
        generated = generate_prior_auth(seed=doc.id.int % (2**32), document_id=str(doc.id))
        buf = io.BytesIO()
        generated.image.convert("RGB").save(buf, format="PNG")
        try:
            key = storage.put_original(
                tenant_id=tenant_id, document_id=doc.id, data=buf.getvalue(), extension=".png"
            )
        except Exception:  # pragma: no cover
            pytest.skip("MinIO not reachable (make local-up)")
        doc.original_object_key = key
        return str(doc.id)


def _make_multipacket_doc(engine, tenant_id: uuid.UUID) -> str:  # type: ignore[no-untyped-def]
    """A RECEIVED upload that CP13 splits into exactly two packets.

    Built around a BLANK SEPARATOR page rather than a feature-distance boundary.
    ``HeuristicSplitter`` has two independent signals and the blank-page one is
    unconditional -- ``gapped`` short-circuits before the distance test -- so this
    fixture does not depend on ``_BOUNDARY_DISTANCE_THRESHOLD`` staying where CP13 tuned
    it. The subject here is the workflow's fan-out, not the splitter's accuracy, and
    coupling the two would make a CP13 retune surface as a CP15 regression.

    It is also the realistic shape: a fax separator sheet is how multi-document faxes
    actually arrive.

    Pages: [prior-auth form] [separator] [insurance card] -> content indices 0 and 2,
    so packet 2's single page must renumber to 1 while still pointing at page-0003.png.
    """
    storage = _object_storage()
    with tenant_context(engine, tenant_id) as s:
        repo = DocumentRepository(s, actor="cp10-test")
        doc = repo.create_document(source_channel="fax", content_hash=uuid.uuid4().hex)
        seed = doc.id.int % (2**32)
        form = generate_prior_auth(seed=seed, document_id=str(doc.id)).image.convert("RGB")
        card = generate_insurance_card(seed=seed, document_id=str(doc.id)).image.convert("RGB")

        separator = Image.new("RGB", form.size, "white")
        # A faint rule rather than pure white: normalize_page's contrast step has no
        # dynamic range to work with on a uniform page. 800px of ink on ~3.7M is 0.02%,
        # far below the 1% blank threshold, so it still reads as a separator.
        ImageDraw.Draw(separator).line(
            [(200, form.height // 2), (600, form.height // 2)], fill=(190, 190, 190), width=2
        )

        buf = io.BytesIO()
        # resolution=200.0 is load-bearing, not decoration. PIL's PDF encoder defaults to
        # 72 DPI, which makes the page BOX 1700x2200 *points* -- a 23.6 x 30.6 inch page.
        # load_pages then renders that at _PDF_RENDER_DPI=200 into 4723x6112: 7.7x the
        # intended pixels and ~19x the normalization cost (3s -> 57s per page), which blew
        # the 30s stage timeout and looked exactly like a fan-out failure. Matching the
        # two DPIs keeps the round trip at the source scale.
        form.save(
            buf, format="PDF", resolution=200.0, save_all=True, append_images=[separator, card]
        )
        pdf_bytes = buf.getvalue()

        # Pin the scale. A regression here does not announce itself -- it reappears as an
        # unexplained stage timeout somewhere far away from this line.
        rendered = load_pages(pdf_bytes, "pdf")
        assert len(rendered) == 3, f"expected 3 pages in the fixture PDF, got {len(rendered)}"
        assert abs(rendered[0].width - form.width) <= 8, (
            f"PDF round-trip changed page scale: rendered {rendered[0].size} from "
            f"{form.size}. save(resolution=...) must match _PDF_RENDER_DPI in "
            "chartwright_preprocess.io."
        )

        try:
            key = storage.put_original(
                tenant_id=tenant_id, document_id=doc.id, data=pdf_bytes, extension=".pdf"
            )
        except Exception:  # pragma: no cover
            pytest.skip("MinIO not reachable (make local-up)")
        doc.original_object_key = key
        return str(doc.id)


def _status_changes(session, entity_id: uuid.UUID) -> list[AuditLog]:  # type: ignore[no-untyped-def]
    return list(
        session.execute(
            select(AuditLog).where(
                AuditLog.entity_id == entity_id, AuditLog.action == "status_change"
            )
        ).scalars()
    )


def _worker(client: Client) -> Worker:
    from concurrent.futures import ThreadPoolExecutor

    activities = PipelineActivities(publisher=LoggingEventPublisher())
    return Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[DocumentPipelineWorkflow],
        activities=[
            activities.advance_stage,
            activities.mark_failed,
            activities.list_packet_children,
        ],
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


class TestPacketFanOut:
    """CP15/ADR-0012. Before this, a multi-packet upload was processed as one document
    and its packet children sat at NORMALIZED forever -- and every other test passed,
    because the gap lived in the workflow layer and nothing ran a workflow over a
    multi-packet document."""

    async def test_packets_run_independently_and_the_upload_completes_after_them(
        self, db, temporal_client
    ) -> None:  # type: ignore[no-untyped-def]
        engine, tenant_id = db
        doc_id = _make_multipacket_doc(engine, tenant_id)
        async with _worker(temporal_client):
            result = await temporal_client.execute_workflow(
                DocumentPipelineWorkflow.run,
                PipelineInput(document_id=doc_id, tenant_id=str(tenant_id)),
                id=f"doc-{doc_id}",
                task_queue=TASK_QUEUE,
            )
        assert result.final_status == "COMPLETED"

        with tenant_context(engine, tenant_id) as s:
            repo = DocumentRepository(s, actor="cp10-test")
            children = repo.list_children(uuid.UUID(doc_id))
            assert len(children) == 2, (
                f"fixture produced {len(children)} packet(s), expected 2 — the blank "
                "separator page did not split the upload. That is a fixture problem, "
                "not a fan-out problem; fix the separator before reading anything else."
            )
            assert [c.packet_index for c in children] == [1, 2]

            # Each packet ran the whole pipeline on its own.
            assert all(c.status == "COMPLETED" for c in children)

            # And ran it exactly once, without re-normalizing: a child is created AT
            # NORMALIZED, so advance_stage no-ops that stage and audits the 8 after it.
            for child in children:
                assert len(_status_changes(s, child.id)) == 8, (
                    f"packet {child.packet_index} audited an unexpected number of "
                    "transitions — a re-run of NORMALIZED would show as 9"
                )

            # The parent is the upload, not a document to extract from: NORMALIZED then
            # straight to COMPLETED, never through CLASSIFIED or EXTRACTED.
            parent = repo.get(uuid.UUID(doc_id))
            assert parent is not None and parent.status == "COMPLETED"
            assert len(_status_changes(s, parent.id)) == 2

            # The separator was dropped, and packet 2's page renumbered to 1 while still
            # pointing at the upload's third page.
            second = repo.get_page(children[1].id, 1)
            assert second is not None
            assert second.image_object_key.endswith("page-0003.png")
            assert repo.get_page(children[1].id, 2) is None


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
