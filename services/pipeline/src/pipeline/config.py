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

    # Retry knobs (small defaults keep integration tests fast; prod raises them via env).
    stage_max_attempts: int = 3
    stage_backoff_seconds: float = 0.2


def get_pipeline_settings() -> PipelineSettings:
    return PipelineSettings()
