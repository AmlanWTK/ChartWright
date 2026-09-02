"""Unit tests: settings + storage-client construction (boto3 builds clients lazily)."""

from pathlib import Path

import pytest
from ingestion.config import Settings, get_settings
from ingestion.storage import ObjectStorage

_REPO_ROOT = Path(__file__).resolve().parents[3]
_COMPOSE = _REPO_ROOT / "infra" / "local" / "docker-compose.yml"
_MINIO_CONTAINER_PORT = "9000"  # fixed by the MinIO image, not by us


class TestSettings:
    def test_dev_defaults_point_at_local_minio(self) -> None:
        s = get_settings()
        assert s.s3_endpoint.startswith("http://localhost:")
        assert s.s3_bucket == "chartwright-documents"
        assert s.max_upload_bytes >= 1024 * 1024

    def test_s3_endpoint_port_matches_the_compose_mapping(self) -> None:
        """Pin the config default to the host port compose actually publishes.

        These are two copies of one fact. Moving MinIO off 9000 took five files by
        hand, and drift between any two of them is silent: the service starts, and
        every S3 call then talks to whatever else owns the old port -- which is the
        exact failure that read as an InvalidAccessKeyId credentials bug for an
        afternoon. Compose is the source of truth; the default has to follow it.
        """
        yaml = pytest.importorskip("yaml")
        compose = yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))
        ports = compose["services"]["minio"]["ports"]
        host_port = next(
            mapping.split(":")[0]
            for mapping in ports
            if mapping.endswith(f":{_MINIO_CONTAINER_PORT}")
        )
        assert get_settings().s3_endpoint.endswith(f":{host_port}"), (
            f"config default {get_settings().s3_endpoint} does not match the port "
            f"docker-compose publishes ({host_port})"
        )


class TestStorageConstruction:
    def test_object_storage_constructs_without_network(self) -> None:
        storage = ObjectStorage(Settings())
        assert storage is not None


class TestIntakeValidationGate:
    """Validation rejects BEFORE any I/O — provable without live services, because
    engine/storage/producer clients all connect lazily."""

    def _service(self):  # type: ignore[no-untyped-def]
        import uuid

        from chartwright_db import build_engine
        from ingestion.events import LoggingEventPublisher
        from ingestion.intake import IntakeService
        from ingestion.scanner import EicarScanner

        service = IntakeService(
            engine=build_engine("postgresql+psycopg://u:p@nonexistent:5/db"),
            storage=ObjectStorage(Settings()),
            scanner=EicarScanner(),
            events=LoggingEventPublisher(),
            settings=Settings(),
        )
        return service, uuid.uuid4()

    def test_engine_property_exposes_shared_engine(self) -> None:
        service, _ = self._service()
        assert service.engine.dialect.name == "postgresql"

    def test_empty_upload_rejected_before_any_io(self) -> None:
        import pytest
        from ingestion.validation import ValidationError

        service, tenant = self._service()
        with pytest.raises(ValidationError) as exc:
            service.submit(tenant_id=tenant, data=b"", source_channel="api")
        assert exc.value.code == "EMPTY_FILE"

    def test_unsupported_type_rejected_before_any_io(self) -> None:
        import pytest
        from ingestion.validation import ValidationError

        service, tenant = self._service()
        with pytest.raises(ValidationError) as exc:
            service.submit(tenant_id=tenant, data=b"MZ\x90 not a document", source_channel="api")
        assert exc.value.code == "UNSUPPORTED_TYPE"
