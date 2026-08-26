"""S3-compatible object storage client (MinIO locally, S3 in production).

Moved out of ``services/ingestion`` in CP13 (ADR-0009) so ``services/pipeline`` can
share it for the ``NORMALIZED`` stage's page storage, without pipeline depending on
the ingestion service. Behavior and key layout are unchanged from the CP09 original:
``tenants/{tenant_id}/documents/{document_id}/original{ext}`` for accepted files,
``quarantine/{tenant_id}/{document_id}{ext}`` for infected ones. CP13 adds
``.../normalized/page-{n}.png`` for normalized page images, and CP15 adds
``.../ocr/page-{n}.json`` for per-page OCR results.
"""

from __future__ import annotations

import uuid
from typing import Any, Protocol

import boto3


class S3SettingsLike(Protocol):
    """Structural type: anything with these five fields can construct an ObjectStorage.

    Both ``ingestion.config.Settings`` and ``pipeline.config.PipelineSettings`` satisfy
    this without either importing the other or this module — that's the point.
    """

    s3_endpoint: str
    s3_access_key: str
    s3_secret_key: str
    s3_bucket: str
    s3_region: str


class ObjectStorage:
    def __init__(self, settings: S3SettingsLike):
        self._bucket = settings.s3_bucket
        self._client: Any = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
            region_name=settings.s3_region,
        )

    def put_original(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID, data: bytes, extension: str
    ) -> str:
        key = f"tenants/{tenant_id}/documents/{document_id}/original{extension}"
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def put_quarantined(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID, data: bytes, extension: str
    ) -> str:
        key = f"quarantine/{tenant_id}/{document_id}{extension}"
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def put_normalized_page(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID, page_number: int, data: bytes
    ) -> str:
        """Store one normalized page image (CP13). ``page_number`` is 1-based."""
        key = f"tenants/{tenant_id}/documents/{document_id}/normalized/page-{page_number:04d}.png"
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    @staticmethod
    def ocr_page_key(*, tenant_id: uuid.UUID, document_id: uuid.UUID, page_number: int) -> str:
        """Deterministic key for one page's OCR result (CP15). ``page_number`` is 1-based.

        Deterministic so the EXTRACTED stage can read what OCR_DONE wrote without a
        database round-trip or a new column -- the key is derivable from ids it already has.
        """
        return f"tenants/{tenant_id}/documents/{document_id}/ocr/page-{page_number:04d}.json"

    def put_ocr_page(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID, page_number: int, data: bytes
    ) -> str:
        """Store one page's serialized OCR result (CP15)."""
        key = self.ocr_page_key(
            tenant_id=tenant_id, document_id=document_id, page_number=page_number
        )
        self._client.put_object(Bucket=self._bucket, Key=key, Body=data)
        return key

    def exists(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self._bucket, Key=key)
        except self._client.exceptions.ClientError:
            return False
        return True

    def get(self, key: str) -> bytes:
        resp = self._client.get_object(Bucket=self._bucket, Key=key)
        body: bytes = resp["Body"].read()
        return body
