# ADR-0004: Postgres as source of truth + Kafka as event log + Temporal for durable workflow

- **Status:** Accepted
- **Date:** 2026-07-27
- **Deciders:** NahidHaque
- **Checkpoint:** CP01 (realized in CP08, CP10)
- **Reversibility:** Mixed — Postgres one-way; Kafka/Temporal replaceable-with-effort

## Context

Following ADR-0001, we need: a strongly-consistent system of record with multi-tenant isolation and immutable audit; a high-throughput, replayable event stream to decouple bursty page processing; and durable per-document orchestration with retries, timers, and long human-in-the-loop waits. No single tool does all three well.

## Options considered

### Option A — One database + hand-rolled queue + hand-rolled workflow
- Pros: Fewer systems.
- Cons: Reinvents durable execution, exactly-once effects, DLQ, and HITL waits; high bug surface in the riskiest area.

### Option B — Postgres (system of record) + Kafka (event log) + Temporal (workflow)
- Pros: Postgres gives ACID, row-level security for tenancy, JSONB for flexible extraction, immutable audit. Kafka gives throughput, buffering, partition-by-tenant fairness, and replay. Temporal gives exactly-once *effects*, retries/backoff, durable timers, and human-wait-as-code.
- Cons: Three systems to operate; conceptual overlap (Kafka vs. Temporal) must be delineated clearly.

### Option C — Cloud-managed queue (SQS) + step functions
- Pros: Managed, less ops.
- Cons: Less portable; weaker local dev; workflow ergonomics and HITL waits less flexible; vendor coupling.

## Decision

Adopt **Option B**. **Postgres** is the source of truth (RLS tenancy, audit, JSONB). **Kafka** carries the high-volume page/stage event stream and provides replay + backpressure. **Temporal** owns the per-document business workflow (state machine, retries, timers, HITL signals). Delineation: *Temporal = per-document correctness; Kafka = high-volume throughput/decoupling.*

## Consequences

- **Positive:** Each concern handled by a purpose-built tool; DB-enforced tenant isolation; deterministic replay; durable human waits without polling hacks.
- **Negative / trade-offs:** Operational surface of three systems; need clear guidance so engineers don't blur Kafka/Temporal responsibilities; overlap requires documentation.
- **Follow-ups:** Schema + RLS in CP08; topics + workflow + DLQ + replay in CP10; revisit managed alternatives only if ops burden proves excessive.

## Links

- ADR-0001 · NFR-AVAIL-*, NFR-SCALE-* · `10-database-design.md`, `13-backend-architecture.md`
