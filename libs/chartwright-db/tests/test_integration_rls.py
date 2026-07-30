"""Integration tests — the CP08 acceptance proof. Requires the local stack (make local-up)
and applied migrations (make db-upgrade). Run: pytest -m integration

Proves, against a real Postgres:
1. Cross-tenant reads return nothing (RLS isolation).
2. No tenant context -> tenant tables appear empty (deny by default).
3. Cross-tenant writes are rejected (WITH CHECK).
4. Every repository write produces an audit row in the same transaction.
5. The app role cannot UPDATE/DELETE audit_log (append-only, DB-enforced).
6. Idempotent document creation by content hash.
"""

import uuid

import pytest
from chartwright_db import (
    AuditLog,
    Document,
    DocumentRepository,
    Tenant,
    admin_database_url,
    build_engine,
    no_tenant_session,
    tenant_context,
)
from sqlalchemy import select, text
from sqlalchemy.exc import ProgrammingError

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def admin_engine():  # type: ignore[no-untyped-def]
    engine = build_engine(admin_database_url())
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover
        pytest.skip("Postgres not reachable — start the local stack (make local-up)")
    return engine


@pytest.fixture(scope="module")
def app_engine():  # type: ignore[no-untyped-def]
    return build_engine()  # app-role URL


@pytest.fixture(scope="module")
def two_tenants(admin_engine) -> tuple[uuid.UUID, uuid.UUID]:  # type: ignore[no-untyped-def]
    """Create two tenants via the admin role (tenants table is not RLS-protected)."""
    a_id, b_id = uuid.uuid4(), uuid.uuid4()
    with no_tenant_session(admin_engine) as s:
        s.add(Tenant(id=a_id, name=f"tenant-a-{a_id.hex[:8]}"))
        s.add(Tenant(id=b_id, name=f"tenant-b-{b_id.hex[:8]}"))
    return a_id, b_id


def _make_doc(engine, tenant_id: uuid.UUID, content_hash: str) -> uuid.UUID:  # type: ignore[no-untyped-def]
    with tenant_context(engine, tenant_id) as s:
        repo = DocumentRepository(s, actor="test-suite")
        doc = repo.create_document(source_channel="api", content_hash=content_hash)
        return doc.id


class TestRLSIsolation:
    def test_tenant_sees_own_document(self, app_engine, two_tenants) -> None:  # type: ignore[no-untyped-def]
        a, _ = two_tenants
        doc_id = _make_doc(app_engine, a, content_hash=uuid.uuid4().hex)
        with tenant_context(app_engine, a) as s:
            assert s.get(Document, doc_id) is not None

    def test_cross_tenant_read_returns_nothing(self, app_engine, two_tenants) -> None:  # type: ignore[no-untyped-def]
        """THE isolation test: tenant B cannot see tenant A's document."""
        a, b = two_tenants
        doc_id = _make_doc(app_engine, a, content_hash=uuid.uuid4().hex)
        with tenant_context(app_engine, b) as s:
            assert s.get(Document, doc_id) is None
            assert s.execute(select(Document).where(Document.id == doc_id)).first() is None

    def test_no_context_sees_nothing(self, app_engine, two_tenants) -> None:  # type: ignore[no-untyped-def]
        a, _ = two_tenants
        _make_doc(app_engine, a, content_hash=uuid.uuid4().hex)
        with no_tenant_session(app_engine) as s:
            assert s.execute(select(Document)).first() is None

    def test_cross_tenant_write_rejected(self, app_engine, two_tenants) -> None:  # type: ignore[no-untyped-def]
        """WITH CHECK: inside tenant B's context you cannot insert rows tagged tenant A."""
        a, b = two_tenants
        with pytest.raises(ProgrammingError), tenant_context(app_engine, b) as s:
            s.add(
                Document(
                    tenant_id=a,  # forged tenant
                    source_channel="api",
                    content_hash=uuid.uuid4().hex,
                )
            )
            s.flush()


class TestAuditOnWrite:
    def test_create_writes_audit_row(self, app_engine, two_tenants) -> None:  # type: ignore[no-untyped-def]
        a, _ = two_tenants
        doc_id = _make_doc(app_engine, a, content_hash=uuid.uuid4().hex)
        with tenant_context(app_engine, a) as s:
            rows = list(
                s.execute(
                    select(AuditLog).where(
                        AuditLog.entity_type == "document",
                        AuditLog.entity_id == doc_id,
                        AuditLog.action == "create",
                    )
                ).scalars()
            )
            assert len(rows) == 1
            assert rows[0].actor == "test-suite"
            assert rows[0].after is not None and rows[0].after["status"] == "RECEIVED"

    def test_status_change_records_before_and_after(self, app_engine, two_tenants) -> None:  # type: ignore[no-untyped-def]
        a, _ = two_tenants
        doc_id = _make_doc(app_engine, a, content_hash=uuid.uuid4().hex)
        with tenant_context(app_engine, a) as s:
            DocumentRepository(s, actor="test-suite").transition_status(doc_id, "NORMALIZED")
        with tenant_context(app_engine, a) as s:
            row = s.execute(
                select(AuditLog).where(
                    AuditLog.entity_id == doc_id, AuditLog.action == "status_change"
                )
            ).scalar_one()
            assert row.before is not None and row.before["status"] == "RECEIVED"
            assert row.after is not None and row.after["status"] == "NORMALIZED"

    def test_audit_log_is_append_only_for_app_role(self, app_engine, two_tenants) -> None:  # type: ignore[no-untyped-def]
        """The app role has no UPDATE/DELETE grant on audit_log — enforced by Postgres."""
        a, _ = two_tenants
        _make_doc(app_engine, a, content_hash=uuid.uuid4().hex)
        with pytest.raises(ProgrammingError), tenant_context(app_engine, a) as s:
            s.execute(text("UPDATE audit_log SET actor = 'tampered'"))


class TestIdempotency:
    def test_same_content_hash_returns_same_document(self, app_engine, two_tenants) -> None:  # type: ignore[no-untyped-def]
        a, _ = two_tenants
        h = uuid.uuid4().hex
        id1 = _make_doc(app_engine, a, content_hash=h)
        id2 = _make_doc(app_engine, a, content_hash=h)
        assert id1 == id2

    def test_same_hash_different_tenant_is_a_new_document(self, app_engine, two_tenants) -> None:  # type: ignore[no-untyped-def]
        a, b = two_tenants
        h = uuid.uuid4().hex
        id_a = _make_doc(app_engine, a, content_hash=h)
        id_b = _make_doc(app_engine, b, content_hash=h)
        assert id_a != id_b
