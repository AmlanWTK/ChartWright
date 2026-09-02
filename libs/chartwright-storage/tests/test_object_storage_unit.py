"""Unit tests: construction + key layout (boto3 clients connect lazily, no network needed)."""

import uuid
from dataclasses import dataclass

import pytest
from botocore.exceptions import ClientError
from chartwright_storage import ObjectStorage


@dataclass
class _FakeSettings:
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "k"
    s3_secret_key: str = "s"  # noqa: S105 — test fixture, not a real credential
    s3_bucket: str = "test-bucket"
    s3_region: str = "us-east-1"


class TestConstruction:
    def test_constructs_without_network(self) -> None:
        storage = ObjectStorage(_FakeSettings())
        assert storage is not None

    def test_satisfies_settings_protocol_structurally(self) -> None:
        """Any object with the five s3_* fields works, no inheritance required —
        this is what lets ingestion.config.Settings and pipeline.config.PipelineSettings
        both construct an ObjectStorage without either importing the other."""
        storage = ObjectStorage(_FakeSettings(s3_bucket="another-bucket"))
        assert storage is not None


class TestKeyLayout:
    """Key format is a stable contract other services reason about; guard it explicitly."""

    def test_original_key_layout(self) -> None:
        storage = ObjectStorage(_FakeSettings())
        tenant_id, doc_id = uuid.uuid4(), uuid.uuid4()
        # put_object isn't called (no real client), but we can inspect the method's
        # key-building logic via a monkeypatched client.
        captured = {}
        storage._client.put_object = lambda **kw: captured.update(kw)  # type: ignore[attr-defined]
        storage.put_original(tenant_id=tenant_id, document_id=doc_id, data=b"x", extension=".pdf")
        assert captured["Key"] == f"tenants/{tenant_id}/documents/{doc_id}/original.pdf"

    def test_normalized_page_key_is_1_based_and_zero_padded(self) -> None:
        storage = ObjectStorage(_FakeSettings())
        tenant_id, doc_id = uuid.uuid4(), uuid.uuid4()
        captured = {}
        storage._client.put_object = lambda **kw: captured.update(kw)  # type: ignore[attr-defined]
        storage.put_normalized_page(
            tenant_id=tenant_id, document_id=doc_id, page_number=3, data=b"x"
        )
        assert captured["Key"] == f"tenants/{tenant_id}/documents/{doc_id}/normalized/page-0003.png"

    def test_quarantine_key_layout(self) -> None:
        storage = ObjectStorage(_FakeSettings())
        tenant_id, doc_id = uuid.uuid4(), uuid.uuid4()
        captured = {}
        storage._client.put_object = lambda **kw: captured.update(kw)  # type: ignore[attr-defined]
        storage.put_quarantined(
            tenant_id=tenant_id, document_id=doc_id, data=b"x", extension=".jpg"
        )
        assert captured["Key"] == f"quarantine/{tenant_id}/{doc_id}.jpg"


class TestReadinessProbe:
    """check_ready exists because exists() cannot tell "absent" from "rejected"."""

    def test_probes_the_configured_bucket(self) -> None:
        storage = ObjectStorage(_FakeSettings(s3_bucket="probe-me"))
        captured = {}
        storage._client.head_bucket = lambda **kw: captured.update(kw)  # type: ignore[attr-defined]
        storage.check_ready()
        assert captured == {"Bucket": "probe-me"}

    def test_rejected_credentials_raise_here_but_are_swallowed_by_exists(self) -> None:
        """The exact distinction the CP09 skip guard depends on.

        exists() answers "is this key here?" and returns False for any ClientError,
        so bad credentials look identical to a missing object. That is why those
        integration tests failed instead of skipping when MinIO was down.
        """
        storage = ObjectStorage(_FakeSettings())

        def _denied(**_: object) -> None:
            raise ClientError({"Error": {"Code": "InvalidAccessKeyId"}}, "HeadBucket")

        storage._client.head_bucket = _denied  # type: ignore[attr-defined]
        storage._client.head_object = _denied  # type: ignore[attr-defined]

        with pytest.raises(ClientError):
            storage.check_ready()
        assert storage.exists("any-key") is False
