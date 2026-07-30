"""Domain-event emission behind a protocol seam.

CP09 emits the ``document.received`` event; the durable Kafka/Temporal backbone that
consumes it is CP10's deliverable. Until then a logging publisher records exactly what
will be published — the call sites and payload contract are final, only the transport
changes when CP10 lands its KafkaEventPublisher. Payloads carry references (IDs), never
PHI, per the threat model.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any, Protocol

logger = logging.getLogger("chartwright.events")


class EventPublisher(Protocol):
    def publish(self, event_type: str, payload: dict[str, Any]) -> None: ...


class LoggingEventPublisher:
    """Dev/CP09 publisher: structured log of the would-be event (no PHI in payloads)."""

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        logger.info("event %s %s", event_type, json.dumps(payload, default=str))


def document_received_event(
    *, tenant_id: uuid.UUID, document_id: uuid.UUID, source_channel: str, dedupe: bool
) -> tuple[str, dict[str, Any]]:
    """The contract for the RECEIVED event (consumed by the CP10 workflow)."""
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
