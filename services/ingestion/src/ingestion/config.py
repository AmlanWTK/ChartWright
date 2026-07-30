"""Ingestion service configuration — everything from environment, dev defaults for CP04-L.

Per ADR-0007's guardrail: code depends on endpoints/config, never on "it's local".
Swapping MinIO for S3 in production is a change to these values, not to code.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHARTWRIGHT_", extra="ignore")

    # Object storage (S3-compatible; MinIO locally, S3 in prod)
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "chartwright"  # dev-only default (CP04-L MinIO)
    # Dev-only default matching the CP04-L MinIO container; real envs MUST override
    # via CHARTWRIGHT_S3_SECRET_KEY. Suppression is deliberate and reviewed.
    s3_secret_key: str = "chartwright_dev"  # noqa: S105
    s3_bucket: str = "chartwright-documents"
    s3_region: str = "us-east-1"

    # Upload limits & accepted types
    max_upload_bytes: int = 50 * 1024 * 1024  # 50 MB
    max_pages_hint: int = 200

    # Service
    service_name: str = "ingestion"


def get_settings() -> Settings:
    return Settings()
