"""Unit tests: topic routing, logging publisher, env-based transport selection."""

import logging

from chartwright_events import (
    KafkaEventPublisher,
    LoggingEventPublisher,
    publisher_from_env,
)
from chartwright_events.topics import (
    EVENT_TOPIC_ROUTING,
    TOPIC_DLQ,
    TOPIC_DOCUMENT_RECEIVED,
)


class TestTopicRouting:
    def test_known_events_route_to_expected_topics(self) -> None:
        assert EVENT_TOPIC_ROUTING["document.received"] == TOPIC_DOCUMENT_RECEIVED
        assert EVENT_TOPIC_ROUTING["document.dlq"] == TOPIC_DLQ

    def test_all_routed_topics_are_namespaced(self) -> None:
        for topic in EVENT_TOPIC_ROUTING.values():
            assert topic.startswith("chartwright."), f"unnamespaced topic: {topic}"


class TestLoggingPublisher:
    def test_publish_logs_event_type_and_payload(self, caplog) -> None:  # type: ignore[no-untyped-def]
        with caplog.at_level(logging.INFO, logger="chartwright.events"):
            LoggingEventPublisher().publish("document.received", {"document_id": "abc"})
        assert "document.received" in caplog.text
        assert "abc" in caplog.text


class TestTransportSelection:
    def test_default_is_logging_publisher(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        monkeypatch.delenv("CHARTWRIGHT_EVENT_PUBLISHER", raising=False)
        assert isinstance(publisher_from_env(), LoggingEventPublisher)

    def test_kafka_selected_by_env(self, monkeypatch) -> None:  # type: ignore[no-untyped-def]
        """Constructor only — librdkafka connects lazily, so no broker is needed."""
        monkeypatch.setenv("CHARTWRIGHT_EVENT_PUBLISHER", "kafka")
        assert isinstance(publisher_from_env(), KafkaEventPublisher)
