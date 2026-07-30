# ADR-0001: Async, event-driven processing pipeline (not a synchronous monolith)

- **Status:** Accepted
- **Date:** 2026-07-27
- **Deciders:** NahidHaque
- **Checkpoint:** CP01 (realized in CP10)
- **Reversibility:** One-way door (foundational)

## Context

Document processing is bursty, long-tailed in latency, and composed of heterogeneous stages with very different resource profiles (I/O-bound ingestion vs. GPU-bound OCR/VLM vs. LLM reasoning). It is also high-stakes and regulated, demanding auditability, idempotency, and the ability to replay any document deterministically (e.g., after a model upgrade).

Constraints: must tolerate traffic spikes without dropping accepted documents; must scale expensive GPU stages independently of cheap ones; must survive partial failures; must support durable human-in-the-loop waits (a reviewer may take hours).

## Options considered

### Option A — Synchronous monolith (request → process → respond)
- Pros: Simplest to build initially; easy local reasoning.
- Cons: Couples all stages; a slow/failed model call blocks the request; cannot scale GPU independently; no natural replay; collapses under burst; long HITL waits impossible.

### Option B — Async event-driven pipeline (durable workflow + message log + stateless workers)
- Pros: Per-stage independent scaling; burst tolerance via buffering/backpressure; idempotent, replayable stages; durable HITL waits; clean failure isolation (bulkheads) and DLQ.
- Cons: More moving parts; requires orchestration + broker; higher initial complexity.

### Option C — Pure queue/worker (e.g., Celery only), no durable workflow engine
- Pros: Lighter than full orchestration.
- Cons: Hand-rolling the state machine, exactly-once effects, timers, and HITL waits is error-prone; reinvents what a workflow engine provides.

## Decision

Adopt **Option B**: an async, event-driven pipeline. A durable workflow engine (Temporal — see ADR-0004) owns the per-document state machine, retries, timers, and HITL waits; a message log (Kafka) carries high-volume page/stage events; stateless, idempotent workers execute one transition each. This is the shape large AI platforms converge on and directly satisfies our burst, scale, resilience, and auditability requirements.

## Consequences

- **Positive:** Independent scaling of GPU vs. I/O stages; no accepted document is ever lost; deterministic replay; durable human waits; failure isolation.
- **Negative / trade-offs:** More infrastructure (broker + workflow engine); a steeper local-dev story; requires idempotency discipline in every worker.
- **Follow-ups:** Define the state machine and idempotency keys in CP10; establish the walking-skeleton (M1) with stubbed stages before real AI logic.

## Links

- NFR-SCALE-*, NFR-AVAIL-*, NFR-PERF-* · ADR-0004 (Postgres/Kafka/Temporal) · `docs/architecture/lifecycle-state-machine.md`
