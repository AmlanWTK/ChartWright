"""chartwright-events: shared event publishing (protocol + logging/Kafka transports)."""

from chartwright_events.publisher import (
    EventPublisher,
    KafkaEventPublisher,
    LoggingEventPublisher,
    publisher_from_env,
)
from chartwright_events.topics import TOPIC_DLQ, TOPIC_DOCUMENT_RECEIVED

__all__ = [
    "TOPIC_DLQ",
    "TOPIC_DOCUMENT_RECEIVED",
    "EventPublisher",
    "KafkaEventPublisher",
    "LoggingEventPublisher",
    "publisher_from_env",
]

__version__ = "0.1.0"
