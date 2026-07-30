"""Unit tests: connection-URL resolution and engine construction (no live DB needed)."""

from chartwright_db import admin_database_url, app_database_url, build_engine


class TestUrlResolution:
    def test_app_url_uses_rls_role_and_local_port(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("CHARTWRIGHT_DATABASE_URL", raising=False)
        url = app_database_url()
        assert "chartwright_app" in url  # the RLS-constrained role, never admin
        assert ":15432/" in url  # high host port (native-Postgres conflict avoidance)

    def test_admin_url_is_distinct_from_app_url(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("CHARTWRIGHT_DATABASE_ADMIN_URL", raising=False)
        assert admin_database_url() != app_database_url()

    def test_env_override_wins(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.setenv("CHARTWRIGHT_DATABASE_URL", "postgresql+psycopg://u:p@h:5/db")
        assert app_database_url() == "postgresql+psycopg://u:p@h:5/db"


class TestEngineConstruction:
    def test_build_engine_is_lazy(self) -> None:
        """Engines connect on first use, so construction needs no live database."""
        engine = build_engine("postgresql+psycopg://u:p@nonexistent-host:5/db")
        assert engine.dialect.name == "postgresql"
