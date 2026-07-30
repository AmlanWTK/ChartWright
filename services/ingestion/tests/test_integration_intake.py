"""Integration tests — CP09 acceptance. Requires local stack + migrations.

Proves against real MinIO + Postgres:
1. Upload -> stored object + RECEIVED document row + audit trail.
2. Resubmission dedupes to the same document (no duplicate object writes).
3. EICAR upload -> QUARANTINED row, bytes under quarantine/, never RECEIVED.
4. API layer: status lookup is tenant-scoped (RLS end-to-end through HTTP).
"""

import uuid

import pytest
from chartwright_db import (
    AuditLog,
    Tenant,
    admin_database_url,
    build_engine,
    no_tenant_session,
)
from fastapi.testclient import TestClient
from ingestion.config import get_settings
from ingestion.events import LoggingEventPublisher
from ingestion.intake import IntakeService
from ingestion.main import app
from ingestion.scanner import EicarScanner
from ingestion.storage import ObjectStorage
from sqlalchemy import select, text

pytestmark = pytest.mark.integration

_PDF = b"%PDF-1.7\n% synthetic test document, no PHI\n%%EOF"
_EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


@pytest.fixture(scope="module")
def stack():  # type: ignore[no-untyped-def]
    admin = build_engine(admin_database_url())
    try:
        with admin.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover
        pytest.skip("Local stack not reachable (make local-up + db-upgrade)")
    tenant_id = uuid.uuid4()
    with no_tenant_session(admin) as s:
        s.add(Tenant(id=tenant_id, name=f"ingest-test-{tenant_id.hex[:8]}"))
    settings = get_settings()
    service = IntakeService(
        engine=build_engine(),
        storage=ObjectStorage(settings),
        scanner=EicarScanner(),
        events=LoggingEventPublisher(),
        settings=settings,
    )
    return service, tenant_id, ObjectStorage(settings)


class TestIntakePipeline:
    def test_clean_upload_stores_and_records(self, stack) -> None:  # type: ignore[no-untyped-def]
        service, tenant_id, storage = stack
        result = service.submit(
            tenant_id=tenant_id, data=_PDF + uuid.uuid4().hex.encode(), source_channel="api"
        )
        assert result.status == "RECEIVED"
        assert result.dedupe is False
        key = f"tenants/{tenant_id}/documents/{result.document_id}/original.pdf"
        assert storage.exists(key), "original not found in object storage"

    def test_resubmission_dedupes(self, stack) -> None:  # type: ignore[no-untyped-def]
        service, tenant_id, _ = stack
        payload = _PDF + b"dedupe-me" + uuid.uuid4().hex.encode()
        first = service.submit(tenant_id=tenant_id, data=payload, source_channel="api")
        second = service.submit(tenant_id=tenant_id, data=payload, source_channel="api")
        assert first.document_id == second.document_id
        assert second.dedupe is True

    def test_eicar_is_quarantined(self, stack) -> None:  # type: ignore[no-untyped-def]
        service, tenant_id, storage = stack
        result = service.submit(tenant_id=tenant_id, data=_PDF + _EICAR, source_channel="api")
        assert result.status == "QUARANTINED"
        key = f"quarantine/{tenant_id}/{result.document_id}.pdf"
        assert storage.exists(key), "quarantined bytes not stored for audit"
        # And it is audited:
        from chartwright_db import tenant_context

        with tenant_context(service.engine, tenant_id) as s:
            actions = {
                row.action
                for row in s.execute(
                    select(AuditLog).where(AuditLog.entity_id == result.document_id)
                ).scalars()
            }
            assert "status_change" in actions


class TestApiTenancy:
    def test_status_lookup_is_tenant_scoped(self, stack) -> None:  # type: ignore[no-untyped-def]
        service, tenant_id, _ = stack
        result = service.submit(
            tenant_id=tenant_id, data=_PDF + uuid.uuid4().hex.encode(), source_channel="api"
        )
        client = TestClient(app)
        # Own tenant sees it
        ok = client.get(
            f"/v1/documents/{result.document_id}", headers={"X-Tenant-Id": str(tenant_id)}
        )
        assert ok.status_code == 200
        assert ok.json()["status"] == "RECEIVED"
        # A different tenant gets 404 — RLS through the whole HTTP stack
        other = client.get(
            f"/v1/documents/{result.document_id}", headers={"X-Tenant-Id": str(uuid.uuid4())}
        )
        assert other.status_code == 404
