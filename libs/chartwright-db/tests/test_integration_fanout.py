"""Integration tests: packet fan-out against a real Postgres (CP15, migration 0003).

These need the database rather than a fake, because what is under test is a *schema*
decision: children reuse their parent's content_hash, which only inserts because migration
0003 made the dedupe index partial (``WHERE parent_document_id IS NULL``). A mocked
repository would cheerfully accept rows Postgres rejects, so the load-bearing assertions
here are ones a unit test structurally cannot make.

Fixture shape follows test_integration_rls.py: the ADMIN role creates tenants (the app
role deliberately has no privilege on the tenants table), the APP role does everything
else — which is also what keeps these tests honest about what the application can do.
"""

import uuid

import pytest
from chartwright_db import (
    Document,
    DocumentRepository,
    NormalizedPageInput,
    Tenant,
    admin_database_url,
    build_engine,
    no_tenant_session,
    tenant_context,
)
from sqlalchemy import text

pytestmark = pytest.mark.integration

_KEY = "tenants/t/documents/p/normalized/"


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
def tenant_id(admin_engine) -> uuid.UUID:  # type: ignore[no-untyped-def]
    """Tenants are created by the admin role; the tenants table is not app-writable."""
    tid = uuid.uuid4()
    with no_tenant_session(admin_engine) as s:
        s.add(Tenant(id=tid, name=f"fanout-{tid.hex[:8]}"))
    return tid


def _parent(repo: DocumentRepository, content_hash: str) -> Document:
    return repo.create_document(source_channel="fax", content_hash=content_hash)


class TestPacketChildren:
    def test_child_reuses_parent_content_hash(self, app_engine, tenant_id) -> None:  # type: ignore[no-untyped-def]
        """The central migration-0003 claim: N packets of one upload all share its hash."""
        digest = uuid.uuid4().hex
        with tenant_context(app_engine, tenant_id) as s:
            repo = DocumentRepository(s, actor="test")
            parent = _parent(repo, digest)
            first = repo.create_child_document(parent, packet_index=1, page_count=2)
            second = repo.create_child_document(parent, packet_index=2, page_count=3)

            assert first.content_hash == digest
            assert second.content_hash == digest
            assert first.parent_document_id == parent.id
            assert second.packet_index == 2
            assert first.status == "NORMALIZED"

    def test_resubmitting_an_upload_with_children_returns_the_parent(  # type: ignore[no-untyped-def]
        self, app_engine, tenant_id
    ) -> None:
        """Dedupe must find the upload, not one of its packets.

        create_document looks up by content_hash with scalar_one_or_none(). Children share
        the parent's hash, so before CP15 scoped that query to `parent_document_id IS NULL`
        this raised MultipleResultsFound — resubmitting a multi-packet fax crashed intake.
        Found by writing this test, not in production.
        """
        digest = uuid.uuid4().hex
        with tenant_context(app_engine, tenant_id) as s:
            repo = DocumentRepository(s, actor="test")
            parent = _parent(repo, digest)
            repo.create_child_document(parent, packet_index=1, page_count=1)
            repo.create_child_document(parent, packet_index=2, page_count=1)
            parent_id = parent.id

        with tenant_context(app_engine, tenant_id) as s:
            repo = DocumentRepository(s, actor="test")
            again = _parent(repo, digest)  # same bytes resubmitted
            assert again.id == parent_id
            assert again.parent_document_id is None

    def test_children_are_listed_in_packet_order(self, app_engine, tenant_id) -> None:  # type: ignore[no-untyped-def]
        with tenant_context(app_engine, tenant_id) as s:
            repo = DocumentRepository(s, actor="test")
            parent = _parent(repo, uuid.uuid4().hex)
            for index in (3, 1, 2):  # inserted out of order on purpose
                repo.create_child_document(parent, packet_index=index, page_count=1)
            assert [c.packet_index for c in repo.list_children(parent.id)] == [1, 2, 3]

    def test_single_packet_document_has_no_children(self, app_engine, tenant_id) -> None:  # type: ignore[no-untyped-def]
        with tenant_context(app_engine, tenant_id) as s:
            repo = DocumentRepository(s, actor="test")
            parent = _parent(repo, uuid.uuid4().hex)
            assert repo.list_children(parent.id) == []

    def test_child_pages_renumber_from_one(self, app_engine, tenant_id) -> None:  # type: ignore[no-untyped-def]
        """A child must look like an ordinary single-packet document downstream: its pages
        start at 1 even though they were pages 4-5 of the upload."""
        with tenant_context(app_engine, tenant_id) as s:
            repo = DocumentRepository(s, actor="test")
            parent = _parent(repo, uuid.uuid4().hex)
            child = repo.create_child_document(parent, packet_index=2, page_count=2)
            repo.record_normalized_pages(
                child.id,
                [
                    NormalizedPageInput(1, 1700, 2200, f"{_KEY}page-0004.png"),
                    NormalizedPageInput(2, 1700, 2200, f"{_KEY}page-0005.png"),
                ],
                normalized_object_key=_KEY,
            )

            first = repo.get_page(child.id, 1)
            assert first is not None
            assert first.image_object_key.endswith("page-0004.png")  # the upload's page 4
            assert repo.get_page(child.id, 3) is None
            assert child.page_count == 2
