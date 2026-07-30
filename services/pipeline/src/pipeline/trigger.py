"""Kafka -> Temporal trigger: consumes document.received, starts the pipeline workflow.

Exactly-once effect from at-least-once delivery: the workflow ID is derived from the
document ID (``doc-{document_id}``) and started with the default ID-reuse policy, so a
redelivered event that tries to start an already-running/completed workflow is rejected
by Temporal — the dedupe is server-side and race-free, not consumer bookkeeping.

Run:  uv run python -m pipeline.trigger
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from chartwright_events import TOPIC_DOCUMENT_RECEIVED
from confluent_kafka import Consumer
from pipeline.config import PipelineSettings, get_pipeline_settings
from pipeline.workflows import DocumentPipelineWorkflow, PipelineInput
from temporalio.client import Client
from temporalio.exceptions import WorkflowAlreadyStartedError

logger = logging.getLogger("chartwright.pipeline.trigger")


def build_consumer(settings: PipelineSettings) -> Consumer:
    consumer = Consumer(
        {
            "bootstrap.servers": settings.kafka_bootstrap,
            "group.id": settings.trigger_group_id,
            "auto.offset.reset": "earliest",
            # Commit AFTER the workflow start succeeds (at-least-once).
            "enable.auto.commit": False,
        }
    )
    consumer.subscribe([TOPIC_DOCUMENT_RECEIVED])
    return consumer


async def start_workflow_for_event(client: Client, payload: dict[str, Any]) -> bool:
    """Start the pipeline for one received event; True if started, False if duplicate."""
    document_id = str(payload["document_id"])
    tenant_id = str(payload["tenant_id"])
    settings = get_pipeline_settings()
    try:
        await client.start_workflow(
            DocumentPipelineWorkflow.run,
            PipelineInput(
                document_id=document_id,
                tenant_id=tenant_id,
                max_attempts=settings.stage_max_attempts,
                backoff_seconds=settings.stage_backoff_seconds,
            ),
            id=f"doc-{document_id}",
            task_queue=settings.task_queue,
        )
        logger.info("started workflow doc-%s", document_id)
        return True
    except WorkflowAlreadyStartedError:
        logger.info("duplicate event for doc-%s ignored (workflow exists)", document_id)
        return False


async def consume_batch(
    client: Client, consumer: Consumer, *, max_messages: int, timeout_s: float
) -> int:
    """Consume up to N messages (used by tests and the main loop). Returns count handled."""
    handled = 0
    for _ in range(max_messages):
        msg = await asyncio.to_thread(consumer.poll, timeout_s)
        if msg is None:
            break
        if msg.error():
            logger.error("kafka error: %s", msg.error())
            continue
        raw = msg.value()
        if raw is None:
            logger.warning("skipping message with empty value")
            consumer.commit(message=msg)
            continue
        payload = json.loads(raw)
        await start_workflow_for_event(client, payload)
        consumer.commit(message=msg)  # commit only after the start attempt resolved
        handled += 1
    return handled


async def run_trigger() -> None:
    settings = get_pipeline_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    consumer = build_consumer(settings)
    logger.info("trigger consuming %s", TOPIC_DOCUMENT_RECEIVED)
    try:
        while True:
            await consume_batch(client, consumer, max_messages=100, timeout_s=1.0)
    finally:
        consumer.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_trigger())


if __name__ == "__main__":
    main()
