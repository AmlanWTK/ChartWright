"""Event publishers: protocol + logging (dev) + Kafka (real transport).

Delivery semantics: at-least-once. The Kafka producer flushes on publish so an accepted
API request implies a durably queued event. Consumers must be idempotent — the pipeline
trigger achieves this via Temporal workflow-ID dedupe (see services/pipeline/trigger.py).
Payloads carry references (IDs), never PHI.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Protocol

from confluent_kafka import Producer

from chartwright_events.topics import EVENT_TOPIC_ROUTING, TOPIC_DLQ

logger = logging.getLogger("chartwright.events")


class EventPublisher(Protocol):
    def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


class LoggingEventPublisher:
    """Dev/test publisher: structured log of the would-be event."""

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        logger.info("event %s %s", event_type, json.dumps(payload, default=str))


class KafkaEventPublisher:
    """Kafka transport. Keyed by document_id so per-document ordering is preserved
    within a partition (the same key the workflow uses for identity)."""

    def __init__(self, bootstrap_servers: str | None = None):
        servers = bootstrap_servers or os.environ.get(
            "CHARTWRIGHT_KAFKA_BOOTSTRAP", "localhost:9092"
        )
        self._producer = Producer({"bootstrap.servers": servers})

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        topic = EVENT_TOPIC_ROUTING.get(event_type, TOPIC_DLQ)
        key = str(payload.get("document_id", "")) or None
        self._producer.produce(
            topic=topic,
            key=key,
            value=json.dumps({"event_type": event_type, **payload}, default=str),
        )
        # Flush so "202 Accepted" implies the event is durably queued (at-least-once).
        # Throughput batching is a tuning knob for later load work (CP30), not v1 intake.
        self._producer.flush(timeout=5.0)


def publisher_from_env() -> EventPublisher:
    """Select the transport by configuration (log|kafka). Default: log (safe everywhere)."""
    kind = os.environ.get("CHARTWRIGHT_EVENT_PUBLISHER", "log").lower()
    if kind == "kafka":
        return KafkaEventPublisher()
    return LoggingEventPublisher()
