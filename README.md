# Chartwright

**Autonomous Clinical Document Intelligence Platform** — a VLM-native system that turns unstructured clinical documents (prior-authorization packets, referrals, EOBs, lab reports, faxed orders) into structured, source-grounded, FHIR-aligned data, and drafts the next action with a human in the loop.

> **Status:** Pre-implementation. We are building checkpoint-by-checkpoint against the plan in [`docs/ROADMAP.md`](docs/ROADMAP.md). This repository currently contains **Checkpoint 1 (CP01) deliverables**: the project charter, architecture decision records, C4 diagrams, requirements traceability, an initial threat model, and team working agreements. No application code yet — that begins at CP02.

---

## What this is

Chartwright is designed as a production-grade platform, not a demo. The core ideas:

- **Cost-aware model cascade** — each page is routed to the cheapest model that can handle it (self-hosted OCR VLM → fine-tuned domain VLM → frontier multimodal API).
- **Grounding contract** — every extracted field carries a bounding box, source span, and calibrated confidence; low-confidence fields route to human review.
- **Policy reasoning via RAG** — payer prior-authorization policies are retrieved and cited, never fabricated.
- **Bounded agent** — a tool-limited, auditable agent assembles the prior-auth packet and emits FHIR (aligned to CMS-0057-F).
- **Evaluation as infrastructure** — a document-level eval harness gates every model/prompt change in CI.

Full rationale lives in the planning package (see `docs/`).

## Repository layout (target)

```
chartwright/
├── README.md                 ← you are here
├── docs/                     ← architecture, decisions, roadmap, governance
│   ├── ROADMAP.md
│   ├── charter.md
│   ├── adr/                  ← architecture decision records
│   ├── architecture/         ← C4 + lifecycle diagrams (Mermaid)
│   ├── traceability-matrix.md
│   ├── threat-model-v0.md
│   ├── working-agreements.md
│   └── definition-of-done.md
├── services/                 ← backend services (from CP02+)
├── frontend/                 ← review console & dashboards (from CP23+)
├── infra/                    ← Terraform + Helm (from CP04+)
├── libs/                     ← shared libraries
└── evals/                    ← eval harness + gold sets (from CP26+)
```

Directories beyond `docs/` are created in their respective checkpoints.

## How we work

One checkpoint at a time. Each is specified, approved, implemented, tested against its Definition of Done, reviewed, and only then marked complete. See [`docs/working-agreements.md`](docs/working-agreements.md) and [`docs/definition-of-done.md`](docs/definition-of-done.md).

## Current checkpoint

**CP04-L — Local Development Platform.** The full backing stack via Docker Compose (`make local-up`): Postgres 16, Kafka (KRaft), Temporal + Web UI, Redis 7, and MinIO (S3-compatible, auto-created `chartwright-documents` bucket) — the same engines production will use, per ADR-0007 (local-first; cloud IaC deferred until GPU serving needs it). Verify with `make local-check`. See [`infra/local/README.md`](infra/local/README.md).

Previously completed — **CP03 — Domain Model, Taxonomy & Synthetic-Data Strategy.** Two workspace libraries:

- `libs/chartwright-schemas` — the shared domain types: the **grounding contract** (every extracted field carries page + bbox + source span + calibrated confidence, enforced by Pydantic), the clinical **document taxonomy**, per-type **extraction schemas** with critical-field marking, and the versioned `ExtractionResult` envelope.
- `libs/chartwright-synthdata` — a deterministic **synthetic document generator** (`uv run synthdata`) producing PA form images with pixel-accurate ground-truth labels and controllable fax-style degradation (`clean`/`fax`/`bad_fax`) — the PHI-free foundation for development and the eval gold sets.

Domain docs: [`docs/domain/taxonomy.md`](docs/domain/taxonomy.md), [`docs/domain/vocabularies.md`](docs/domain/vocabularies.md), [`docs/domain/gold-set-structure.md`](docs/domain/gold-set-structure.md).

CP01 (architecture baseline) and CP02 (tooling + CI) are complete — see `docs/ROADMAP.md`.
