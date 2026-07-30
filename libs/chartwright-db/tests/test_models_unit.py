"""Unit tests (no database): structural invariants of the model layer."""

from chartwright_db.models import RLS_TABLES, Base


class TestTenancyInvariants:
    def test_every_rls_table_exists_in_metadata(self) -> None:
        table_names = set(Base.metadata.tables)
        for name in RLS_TABLES:
            assert name in table_names, f"RLS table '{name}' missing from metadata"

    def test_every_tenant_owned_table_has_tenant_id(self) -> None:
        """The structural precondition for RLS: no tenant table without tenant_id."""
        for name in RLS_TABLES:
            table = Base.metadata.tables[name]
            assert "tenant_id" in table.c, f"table '{name}' lacks tenant_id"

    def test_only_tenants_table_is_outside_rls(self) -> None:
        """Any new table must either carry tenant_id + RLS or be explicitly exempt.

        This test fails when someone adds a table and forgets to add it to RLS_TABLES —
        making 'forgot the security' a red build instead of a silent hole.
        """
        exempt = {"tenants", "alembic_version"}
        for name, table in Base.metadata.tables.items():
            if name in exempt:
                continue
            assert name in RLS_TABLES, (
                f"table '{name}' is not in RLS_TABLES and not exempt — add RLS or justify exemption"
            )
            assert "tenant_id" in table.c

    def test_audit_log_has_before_after_and_actor(self) -> None:
        audit = Base.metadata.tables["audit_log"]
        for col in ("actor", "action", "entity_type", "entity_id", "before", "after"):
            assert col in audit.c

    def test_documents_dedupe_index_exists(self) -> None:
        doc = Base.metadata.tables["documents"]
        unique_index_cols = [tuple(c.name for c in ix.columns) for ix in doc.indexes if ix.unique]
        assert ("tenant_id", "content_hash") in unique_index_cols
