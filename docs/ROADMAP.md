# Chartwright — Roadmap (Repo Summary)

This is the in-repo summary of the execution plan. The 34 checkpoints are delivered one at a time; each is specified, approved, built, tested against its Definition of Done, and reviewed before the next begins.

> The detailed per-checkpoint specifications (objective, tasks, deliverables, success criteria, edge cases, risks, DoD, execution log) are maintained alongside this roadmap as `CPxx-*.md` files in the planning package.

## Phases

| Phase | Theme | Checkpoints |
|-------|-------|-------------|
| A | Planning & Foundations | CP01–CP03 |
| B | Infrastructure & Platform | CP04–CP07 |
| C | Data & Ingestion Backbone | CP08–CP10 |
| D | AI Core | CP11–CP20 |
| E | Application & Frontend | CP21–CP25 |
| F | Quality, Flywheel & Security | CP26–CP29 |
| G | Scale, Cost & Launch | CP30–CP34 |

## Checkpoints & status

**Legend:** ⬜ Not started · 🟡 In progress · 🔵 In review · ✅ Done

| # | Checkpoint | Depends on | Status |
|---|-----------|-----------|--------|
| CP01 | Project charter, ADRs & architecture baseline | — | ✅ Done |
| CP02 | Repository, tooling & CI foundation | CP01 | ✅ Done |
| CP03 | Domain model, taxonomy & synthetic-data strategy | CP01 | ✅ Done |
| CP04-L | **Local development platform (Docker Compose)** — replaces CP04 sequencing per ADR-0007; cloud IaC deferred | CP02 | ✅ Done |
| CP04 | Infrastructure as Code & cloud environments | CP02 | ⏸ Deferred (ADR-0007) |
| CP05 | Kubernetes platform & GitOps delivery | CP04 | ⏸ Deferred (ADR-0007) |
| CP06 | Observability & platform scaffolding | CP05 | ⬜ |
| CP07 | Identity, secrets & baseline security controls | CP05 | ⬜ |
| CP08 | Data model & persistence layer (Postgres, RLS, audit) | CP04-L, CP03 | ✅ Done |
| CP09 | Object storage & document intake service | CP08 (CP07 deferred: dev tenant header) | ✅ Done |
| CP10 | Workflow orchestration (Temporal) & event backbone (Kafka) | CP09 (CP06 observability deferred per ADR-0007) | ✅ Done — **Milestone 1 complete** |
| CP11 | Model Gateway (router, provider abstraction, metering) — Ollama local per ADR-0008 | CP10 | ✅ Done |
| CP12 | Tier-0 OCR + grounding contract (RapidOCR local; vLLM/GPU deferred to cloud re-entry) | CP11 | ✅ Done |
| CP13 | Preprocessing, normalization & packet splitting | CP12 | ✅ Done |
| CP14 | Document classification (describe-then-map per ADR-0010) | CP13 | ✅ Done |
| CP15 | Structured extraction (grounded, schema-constrained) | CP14 | ✅ Done |
| CP16 | Validation, normalization & code systems | CP15 | ⬜ |
| CP17 | Confidence calibration & escalation cascade | CP16 | ⬜ |
| CP18 | Policy KB ingestion & vector store | CP11 | ⬜ |
| CP19 | RAG retrieval & grounded policy reasoning | CP18, CP16 | ⬜ |
| CP20 | Agentic orchestration (bounded tools + HITL waits) | CP17, CP19 | ⬜ |
| CP21 | External API layer & webhooks | CP10 | ⬜ |
| CP22 | FHIR output & delivery | CP16, CP21 | ⬜ |
| CP23 | Frontend foundation, design system & auth | CP07, CP21 | ⬜ |
| CP24 | Human-in-the-loop review console | CP23, CP17, CP20 | ⬜ |
| CP25 | Admin/ops dashboards & developer portal | CP23, CP06 | ⬜ |
| CP26 | Evaluation harness & CI regression gates | CP15, CP19, CP20 | ⬜ |
| CP27 | Dataset creation, annotation & de-identification | CP24, CP26 | ⬜ |
| CP28 | Domain fine-tuning (Tier-1 moat) & promotion | CP27 | ⬜ |
| CP29 | Security hardening & compliance readiness | CP07, CP24 | ⬜ |
| CP30 | Load, scalability & resilience/chaos testing | CP20, CP22 | ⬜ |
| CP31 | Disaster recovery & business continuity | CP30 | ⬜ |
| CP32 | Cost optimization & FinOps | CP17, CP30 | ⬜ |
| CP33 | Pilot / ROI validation & benchmarking | CP24, CP26 | ⬜ |
| CP34 | Production launch, runbooks & continuous improvement | CP29, CP31, CP32, CP33 | ⬜ |

## Milestones (demo-able releases)

- **M1 — Walking skeleton** (CP01–CP10): a document flows end-to-end through a durable pipeline with stubbed AI.
- **M2 — It reads** (CP11–CP17): grounded OCR + extraction + confidence + cascade.
- **M3 — It reasons** (CP18–CP20): policy RAG + bounded agent assembling a PA packet.
- **M4 — It's a product** (CP21–CP25): APIs, FHIR, review console, dashboards.
- **M5 — It's trustworthy** (CP26–CP29): eval gates, fine-tune, compliance.
- **M6 — It's production** (CP30–CP34): scale/DR proven, cost controlled, launched.

**Current progress:** CP01–CP03, CP04-L and CP08–CP15 done (CP04/CP05 deferred, CP06/CP07 partially deferred, per ADR-0007) — **Milestone 1 (walking skeleton) COMPLETE** and **Milestone 2 (*It reads*) at 5/7**: Tier-0 OCR with a real grounding contract (CP12), pixel-only page normalization + structural packet splitting (CP13), document classification at 98.3% (CP14), and deterministic label-anchored extraction at 98.5% with multi-packet fan-out proven end-to-end against a live Temporal (CP15). Next: **CP16 — Validation, normalization & code systems** · 11/34 complete. Cloud checkpoints (CP04/CP05 and the managed parts of CP06/CP07) are deferred per ADR-0007 and re-enter no later than just before GPU-served Tier-0 OCR.
