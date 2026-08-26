# Chartwright

**Autonomous Clinical Document Intelligence Platform** — a VLM-native system that turns unstructured clinical documents (prior-authorization packets, referrals, EOBs, lab reports, faxed orders) into structured, source-grounded, FHIR-aligned data, and drafts the next action with a human in the loop.

> **Status:** Active development. We are building checkpoint-by-checkpoint against the plan in [`docs/ROADMAP.md`](docs/ROADMAP.md) — CP01–CP14 complete (10/34; Milestone 1 walking skeleton done, Phase D AI core underway). See "Current checkpoint" below for what's implemented today.

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

**CP14 — Document Classification.** `libs/chartwright-classify`: the pipeline's first model-calling stage. The Tier-0 model describes the page in free text and a deterministic keyword mapper turns that description into exactly one `DocType` — **the model does perception, code owns the ontology** (ADR-0010). The obvious design, asking the model to pick one of nine codes under a constrained grammar, was built first and measured **28.3%**: the grammar guarantees schema-valid output, which hid the fact that a 1.6B model given a 158-token enumerated prompt was emitting two tokens of garbage. Asked simply to describe the same page it reads it correctly. Rebuilt around that, plus a rewritten `insurance_card` generator (the old one drew a near-blank page — the eval had been measuring its own scaffolding): `uv run python scripts/eval_classify.py --count 20` — gate ≥ 85%, **measured 98.3%** (fitted to the synthetic set; CP26's gold set is the real test). Unrecognizable pages map to `OTHER` at 0.0 confidence and route to human review — never a confident guess. Full measurement trail in [`docs/CP14-document-classification.md`](docs/CP14-document-classification.md).

Previously completed — **CP13 — Preprocessing, Normalization & Packet Splitting.** `libs/chartwright-preprocess`: pixel-only, deterministic prep between CP09 intake and CP14 classification — no model calls, same discipline as CP12's Tier-0 OCR. `normalize_page` corrects 0/90/180/270 orientation (row-projection-variance axis test + upper/lower ink-asymmetry tie-break) and fine skew (narrow-range projection search); `HeuristicSplitter` partitions a multi-page upload into logical documents ("packets") using structural signals only (blank-separator detection + feature-distance thresholding), since neither classification nor OCR text exists yet at the `NORMALIZED` stage. `libs/chartwright-storage` was extracted from `services/ingestion` (ADR-0009) so `services/pipeline` can share object storage without a service-to-service dependency; the pipeline's `NORMALIZED` stage now does real work end to end — rasterize the stored original, normalize each page, persist it, split into packets, all audited via the existing repository (no schema change). Measured against synthetic gates: `uv run python scripts/eval_preprocess.py` (orientation accuracy ≥ 95%, split precision/recall ≥ 85%; current baseline is 100% across all conditions). Verified against the live local stack via `uv run pytest -m integration`.

Previously completed — **CP12 — Tier-0 OCR & the Grounding Contract.** `libs/chartwright-ocr`: RapidOCR (pip-only ONNX, CPU, real per-token bounding boxes) behind an `OcrEngine` protocol, tokens assembled in reading order, and the ADR-0003 grounding mechanics live: `locate_value` finds a value's physical evidence or returns None (never invents coordinates), `verify_at` audits location claims — the anti-hallucination check that will police VLM extractor output in CP15. Measured against pixel-accurate synthetic gold labels per degradation slice: `uv run python scripts/eval_ocr.py` (gate: clean-slice field recall ≥ 90%).

Previously completed — **CP11 — Model Gateway (Phase D: the AI core begins).** `libs/chartwright-gateway`: every model call in the system goes through `ModelGateway.generate()` — per-tier provider chains with failover, content-hash response caching (identical request never hits an engine twice), circuit breaking (dead engines get skipped, not waited on), and per-tenant metering (the future dashboard's data feed). Local engine: **Ollama** (`ollama pull moondream`) per ADR-0008 — zero cost, provider-swappable via the `ModelProvider` protocol; the frontier tier is a labeled mock until an API key is configured.

Previously completed — **CP10 — Workflow Orchestration (Milestone 1: the walking skeleton).** `services/pipeline` + `libs/chartwright-events`: a Temporal workflow durably walks every document through the full state machine with per-stage retries and idempotent, audited transitions; ingestion now publishes real `document.received` events to Kafka (`CHARTWRIGHT_EVENT_PUBLISHER=kafka`); a trigger service consumes them and starts workflows with server-side duplicate rejection (exactly-once starts from at-least-once delivery); poisoned documents land in FAILED + a DLQ event and can be replayed to COMPLETED (`scripts/replay_document.py`). Stage bodies are stubs — CP13+ fill in real AI work without changing the workflow shape. Watch it live in the Temporal UI: http://localhost:8233.

Previously completed — **CP09 — Object Storage & Document Intake.** `services/ingestion`: the pipeline's front door. Magic-byte file validation (client-declared types are never trusted), malware scanning behind a `Scanner` protocol (EICAR engine locally, quarantine path proven end-to-end), sha256 per-tenant dedupe, MinIO/S3 storage with tenant-prefixed keys, audited persistence via CP08 repositories, and the `document.received` event contract for CP10. Run: `make run-ingestion` → http://localhost:8100/docs.

Previously completed — **CP08 — Data Model & Persistence Layer.** `libs/chartwright-db`: SQLAlchemy 2.0 typed models for the relational spine (tenants, documents, pages, grounded extractions, review tasks, audit), with three production guarantees: **DB-enforced tenant isolation** (row-level security keyed to a per-transaction tenant context, app connects as a non-superuser role), **audit-on-write** (append-only `audit_log` written in the same transaction, UPDATE/DELETE physically ungranted), and **migrations-only schema** (Alembic). Verified by integration tests that actively attempt cross-tenant reads/writes and audit tampering. `make db-upgrade && make db-seed && make test-integration`.

Previously completed — **CP04-L — Local Development Platform.** The full backing stack via Docker Compose (`make local-up`): Postgres 16, Kafka (KRaft), Temporal + Web UI, Redis 7, and MinIO (S3-compatible, auto-created `chartwright-documents` bucket) — the same engines production will use, per ADR-0007 (local-first; cloud IaC deferred until GPU serving needs it). Verify with `make local-check`. See [`infra/local/README.md`](infra/local/README.md).

Previously completed — **CP03 — Domain Model, Taxonomy & Synthetic-Data Strategy.** Two workspace libraries:

- `libs/chartwright-schemas` — the shared domain types: the **grounding contract** (every extracted field carries page + bbox + source span + calibrated confidence, enforced by Pydantic), the clinical **document taxonomy**, per-type **extraction schemas** with critical-field marking, and the versioned `ExtractionResult` envelope.
- `libs/chartwright-synthdata` — a deterministic **synthetic document generator** (`uv run synthdata`) producing PA form images with pixel-accurate ground-truth labels and controllable fax-style degradation (`clean`/`fax`/`bad_fax`) — the PHI-free foundation for development and the eval gold sets.

Domain docs: [`docs/domain/taxonomy.md`](docs/domain/taxonomy.md), [`docs/domain/vocabularies.md`](docs/domain/vocabularies.md), [`docs/domain/gold-set-structure.md`](docs/domain/gold-set-structure.md).

CP01 (architecture baseline) and CP02 (tooling + CI) are complete — see `docs/ROADMAP.md`.
