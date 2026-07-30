# chartwright-events

Shared event plumbing (CP10): the `EventPublisher` protocol, topic names, and two
implementations — `LoggingEventPublisher` (dev/tests) and `KafkaEventPublisher` (the real
transport). Payloads carry **references only, never PHI** (threat-model rule; asserted by
ingestion's event-contract test).

Topics:

| Topic | Producer | Consumer |
|-------|----------|----------|
| `chartwright.documents.received` | ingestion | pipeline trigger (starts the Temporal workflow) |
| `chartwright.dlq` | pipeline (on exhausted retries) | ops tooling / replay |

Publisher selection is configuration (`CHARTWRIGHT_EVENT_PUBLISHER=log|kafka`), per the
ADR-0007 guardrail: transports are swappable without touching call sites.
