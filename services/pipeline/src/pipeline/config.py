"""Pipeline configuration — env-driven, dev defaults matching the CP04-L stack."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class PipelineSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHARTWRIGHT_", extra="ignore")

    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    task_queue: str = "chartwright-pipeline"

    kafka_bootstrap: str = "localhost:9092"
    trigger_group_id: str = "chartwright-pipeline-trigger"

    # Object storage (S3-compatible; MinIO locally, S3 in prod). Defaults match
    # ingestion.config.Settings exactly — same CP04-L MinIO container, same bucket.
    s3_endpoint: str = "http://localhost:9000"
    s3_access_key: str = "chartwright"  # dev-only default (CP04-L MinIO)
    s3_secret_key: str = "chartwright_dev"  # noqa: S105
    s3_bucket: str = "chartwright-documents"
    s3_region: str = "us-east-1"

    # Retry knobs (small defaults keep integration tests fast; prod raises them via env).
    stage_max_attempts: int = 3
    stage_backoff_seconds: float = 0.2


def get_pipeline_settings() -> PipelineSettings:
    return PipelineSettings()
