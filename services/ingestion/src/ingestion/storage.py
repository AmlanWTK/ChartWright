"""S3-compatible object storage client (MinIO locally, S3 in production).

Key layout: ``tenants/{tenant_id}/documents/{document_id}/original{ext}`` for accepted
files, ``quarantine/{tenant_id}/{document_id}{ext}`` for infected ones. Per-tenant
prefixes are the local analogue of the per-tenant KMS keys planned for S3.
"""

from __future__ import annotations

import uuid
from typing import Any

import boto3

from ingestion.config import Settings


class ObjectStorage:
    def __init__(self, settings: Settings):
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
