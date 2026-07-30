"""Ingestion's event contract. Transports live in chartwright-events (CP10).

The publisher implementations moved to the shared ``chartwright_events`` library when the
Kafka transport landed; this module keeps the ingestion-domain event *builder* and
re-exports the publisher types its callers/tests use. Payloads: references only, no PHI.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from chartwright_events import (
    EventPublisher,
    KafkaEventPublisher,
    LoggingEventPublisher,
    publisher_from_env,
)

__all__ = [
    "EventPublisher",
    "KafkaEventPublisher",
    "LoggingEventPublisher",
    "document_received_event",
    "publisher_from_env",
]


def document_received_event(
    *, tenant_id: uuid.UUID, document_id: uuid.UUID, source_channel: str, dedupe: bool
) -> tuple[str, dict[str, Any]]:
    """The contract for the RECEIVED event (consumed by the CP10 pipeline trigger)."""
    return (
        "document.received",
        {
            "tenant_id": str(tenant_id),
            "document_id": str(document_id),
            "source_channel": source_channel,
            "dedupe": dedupe,
            "occurred_at": datetime.now(tz=UTC).isoformat(),
        },
    )
