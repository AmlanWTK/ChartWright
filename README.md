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

**CP02 — Repository, Tooling & CI Foundation.** Monorepo scaffold (`services/`, `frontend/`, `libs/`), quality gates (Ruff, mypy, ESLint, Prettier, TypeScript), pre-commit hooks, Conventional Commits, and GitHub Actions CI (lint → type → test → build → security scans). A reference `hello` service and frontend package prove the CI lanes. See [`CONTRIBUTING.md`](CONTRIBUTING.md) to set up your environment.

CP01 (charter, ADRs, C4 diagrams, traceability, threat model, governance) is complete — see `docs/`.
