# Requirements Traceability Matrix

Maps functional (FR) and non-functional (NFR) requirements to the checkpoint(s) that implement them and the test/eval category that verifies them. No requirement is "done" until it has a passing test and, where applicable, an eval metric.

> Requirement IDs reference the planning package (`06-functional-requirements.md`, `07-non-functional-requirements.md`). This matrix is maintained as requirements and checkpoints evolve.

## Functional requirements

| FR group | Requirement (summary) | Primary checkpoint(s) | Verified by |
|----------|-----------------------|-----------------------|-------------|
| FR-ING | Multi-channel ingestion, formats, dedupe, malware scan | CP09 | Integration + idempotency + malware tests |
| FR-PRE | Deskew/denoise, packet splitting, quality scoring | CP13 | Boundary + quality tests |
| FR-CLS | Document classification + confidence | CP14 | Classification eval (confusion matrix, ECE) |
| FR-EXT | Grounded field/table extraction, provenance, confidence, normalization | CP12, CP15, CP16 | Extraction + grounding + hallucination eval |
| FR-RSN | PA-requirement + medical-necessity reasoning with citations | CP19 | RAG eval (citation-support, refusal) |
| FR-AGT | Bounded agent orchestration, HITL waits, trace | CP20 | Scenario + injection + replay tests |
| FR-HITL | Review console, overlays, corrections, queue | CP24 | E2E + usability + a11y |
| FR-OUT | FHIR output, packet, delivery, status | CP22 | FHIR conformance + delivery tests |
| FR-PLT | Multi-tenancy, audit, dashboards, config, data rights | CP08, CP25, CP29 | RLS + audit + admin tests |
| FR-EVAL | Gold sets, CI gates, feedback capture, drift | CP26, CP27 | Canary-regression + drift-alert tests |

## Non-functional requirements

| NFR group | Target (summary) | Primary checkpoint(s) | Verified by |
|-----------|------------------|-----------------------|-------------|
| NFR-PERF | Median < 15s; p95 < 5 min; ingest ack < 300ms | CP09, CP17, CP30 | Load tests, prod SLO |
| NFR-SCALE | ≥ 1M pages/day + 3× burst; linear scaling | CP10, CP30 | Load + autoscale tests |
| NFR-AVAIL | 99.9% API; no accepted doc lost; RPO≤5m/RTO≤1h | CP10, CP31 | Chaos + DR drill |
| NFR-ACC | Critical-field ≥95%; ECE ≤0.05; hallucination ≤0.5% | CP15, CP17, CP26 | Eval harness |
| NFR-COST | Cost/page under ceiling; ≥70% cheap tier; GPU ≥60% | CP17, CP32 | Cost telemetry |
| NFR-SEC | HIPAA safeguards; encryption; RLS; SOC 2 readiness | CP07, CP08, CP29 | Pen test, isolation test, scans |
| NFR-OBS | 100% tracing; PHI-safe logs; golden dashboards | CP06 | Trace coverage, redaction test |
| NFR-MAINT | ≥80% coverage; CI <15m; reproducible IaC | CP02, CP04 | CI metrics, fresh rebuild |
| NFR-UX | Reviewer ≤3 min/doc; WCAG 2.1 AA | CP24 | Usability + a11y audit |
| NFR-PORT | Provider abstraction; cloud-portable core | CP11, CP04 | Adapter + IaC review |

## Guiding principles → mechanisms

| Charter principle | Enforced by | Checkpoint |
|-------------------|-------------|------------|
| Grounding over guessing | ADR-0003 grounding contract | CP12, CP15 |
| Right model for the page | ADR-0002 Model Gateway cascade | CP11, CP17 |
| Human-in-the-loop by design | Review console + durable HITL waits | CP20, CP24 |
| Evaluation is infrastructure | ADR-0006 eval CI gate | CP26 |
| Compliance is architectural | RLS, audit, PHI minimization | CP07, CP08, CP29 |
| Async, idempotent, replayable | ADR-0001/0004 pipeline | CP10 |

## Coverage check

Every FR/NFR group above maps to at least one checkpoint and one verification method. **No gaps** at CP01. This matrix is a CP01 Definition-of-Done artifact and is revisited whenever requirements change.
