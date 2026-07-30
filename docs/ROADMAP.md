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
| CP02 | Repository, tooling & CI foundation | CP01 | 🔵 In review |
| CP03 | Domain model, taxonomy & synthetic-data strategy | CP01 | ⬜ |
| CP04 | Infrastructure as Code & cloud environments | CP02 | ⬜ |
| CP05 | Kubernetes platform & GitOps delivery | CP04 | ⬜ |
| CP06 | Observability & platform scaffolding | CP05 | ⬜ |
| CP07 | Identity, secrets & baseline security controls | CP05 | ⬜ |
| CP08 | Data model & persistence layer (Postgres, RLS, audit) | CP04, CP03 | ⬜ |
| CP09 | Object storage & document intake service | CP08, CP07 | ⬜ |
| CP10 | Workflow orchestration (Temporal) & event backbone (Kafka) | CP09, CP06 | ⬜ |
| CP11 | Model Gateway (router, provider abstraction, metering) | CP10 | ⬜ |
| CP12 | GPU serving (vLLM) & Tier-0 OCR VLM + grounding | CP11 | ⬜ |
| CP13 | Preprocessing, normalization & packet splitting | CP12 | ⬜ |
| CP14 | Document classification | CP13 | ⬜ |
| CP15 | Structured extraction (grounded, schema-constrained) | CP14 | ⬜ |
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

**Current progress:** CP01 done · CP02 in review · 1/34 complete.
