# Document Lifecycle — State Machine

The per-document workflow owned by the Temporal orchestration service (ADR-0001, ADR-0004). Every transition is an event persisted with a version + correlation ID; stages are idempotent and replayable.

```mermaid
stateDiagram-v2
    [*] --> RECEIVED
    RECEIVED --> VALIDATED: file valid, scanned
    RECEIVED --> QUARANTINED: malware / bad file
    VALIDATED --> NORMALIZED: deskew, denoise, split packet
    NORMALIZED --> CLASSIFIED: doc type + confidence
    CLASSIFIED --> OCR_DONE: grounded OCR (VLM cascade)
    OCR_DONE --> EXTRACTED: grounded fields + tables
    EXTRACTED --> VALIDATED_FIELDS: code/format validation
    VALIDATED_FIELDS --> POLICY_CHECKED: RAG policy reasoning
    POLICY_CHECKED --> NEEDS_REVIEW: low confidence / ambiguity
    POLICY_CHECKED --> PACKET_ASSEMBLED: straight-through
    NEEDS_REVIEW --> REVIEWED: human resolves
    REVIEWED --> PACKET_ASSEMBLED
    PACKET_ASSEMBLED --> OUTPUT_EMITTED: FHIR + packet
    OUTPUT_EMITTED --> COMPLETED
    COMPLETED --> [*]

    RECEIVED --> FAILED: unrecoverable error
    NORMALIZED --> FAILED
    OCR_DONE --> FAILED
    EXTRACTED --> FAILED
    FAILED --> [*]
    QUARANTINED --> [*]
```

**Notes:**
- `FAILED` messages land in a **dead-letter queue** with a structured reason and can be **replayed** deterministically after a fix or model upgrade.
- `NEEDS_REVIEW` is a **durable Temporal wait** (`request_human_input`) — the workflow pauses without polling until a reviewer acts.
- Confidence/policy thresholds (per tenant/field) decide the `NEEDS_REVIEW` vs. straight-through branch.
- Idempotency key for every transition: `document_id + stage + input_hash` → exactly-once *effects* under at-least-once delivery.
