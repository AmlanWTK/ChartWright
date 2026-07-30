"""Topic names — one place, so producers and consumers can never drift."""

TOPIC_DOCUMENT_RECEIVED = "chartwright.documents.received"
TOPIC_DLQ = "chartwright.dlq"

# event_type -> topic routing. Events not listed here go to the DLQ topic prefix rule
# below rather than silently disappearing.
EVENT_TOPIC_ROUTING: dict[str, str] = {
    "document.received": TOPIC_DOCUMENT_RECEIVED,
    "document.dlq": TOPIC_DLQ,
}
