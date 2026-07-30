# Chartwright — Project Charter

**Document owner:** NahidHaque · **Status:** Draft for approval · **Checkpoint:** CP01

---

## 1. Purpose

Chartwright exists to eliminate the manual, expensive, error-prone work of reading and re-keying unstructured clinical documents — beginning with **prior authorization (PA)** — by turning those documents into structured, verifiable, FHIR-aligned data and drafting the next action, with a human accountable at every consequential step.

## 2. Problem (one sentence)

US healthcare spends tens of billions of dollars a year having humans manually read, re-key, and route clinical documents — most acutely in prior authorization — because the documents are unstructured, degraded, and heterogeneous, and existing automation breaks on exactly the messy cases that dominate real volume.

## 3. Why now

- **Model capability crossed the threshold:** 2025–2026 vision-language models read degraded faxes, handwriting, and complex tables as a single layout-aware model.
- **Regulatory forcing function:** CMS-0057-F requires impacted payers to run a FHIR **Prior Authorization API** (and three other FHIR APIs) by **January 1, 2027**, with operational provisions from Jan 1, 2026.
- **Economic pressure:** thin margins make administrative-cost reduction a board-level priority.

## 4. Vision

> Turn any clinical document — however degraded — into structured, source-grounded, FHIR-aligned data that a machine or clinician can trust, then act on it.

## 5. In scope (v1)

- Ingestion of PDF, multi-page TIFF/fax, images, and FHIR `DocumentReference` attachments.
- Classification across a clinical document taxonomy.
- Grounded field + table extraction with confidence and provenance.
- RAG over a payer prior-authorization policy knowledge base.
- One fully agentic workflow: **prior-authorization packet assembly + determination support**, emitting FHIR.
- Human-in-the-loop review console.
- Multi-tenant SaaS with observability, an eval harness, and a HIPAA-grade security posture.

## 6. Explicit non-goals (v1)

- **No autonomous clinical or coverage decisions.** Chartwright *drafts and recommends*; a human or the payer's rules engine decides. This is a deliberate safety, liability, and regulatory boundary.
- **No foundation model of our own.** We route across and fine-tune existing models.
- **No deep EHR write-back** beyond standards-based FHIR in v1.
- **No consumer product.** B2B / B2B2C only.

## 7. Success metrics

**Product (v1 targets):**
- ≥ 90% straight-through on the clean-typed tier; ≥ 70% blended.
- Critical-field accuracy ≥ 95% on the internal gold set (member ID, CPT, ICD-10, DOS, ordering NPI).
- Median turnaround < 60s; p95 < 5 min for standard packets.
- Reviewer time reduction ≥ 60% vs. manual baseline.
- Hallucinated-field rate ≤ 0.5%.

**Engineering:**
- Every model/prompt/router change eval-gated in CI.
- DB-enforced tenant isolation; no PHI in logs.
- Reproducible infrastructure from code.

## 8. Stakeholders & personas

| Persona | Role |
|---------|------|
| Prior-auth coordinator / medical biller | Primary reviewer (lives in the review console) |
| Revenue-cycle operations leader | Economic buyer |
| Payer utilization-management team | Receives FHIR-structured requests |
| Platform / ML engineer | Builds and operates the system |

## 9. Guiding principles (non-negotiable)

1. **Grounding over guessing** — no field without box + span + calibrated confidence.
2. **Right model for the page** — cost-aware routing; never a frontier model on a clean page.
3. **Human-in-the-loop by design** — uncertainty is surfaced and routed, not hidden.
4. **Evaluation is infrastructure** — regression gates in CI.
5. **Compliance is architectural** — tenancy, auditability, PHI minimization baked in.
6. **Async, idempotent, replayable** — every stage durable and reprocessable.

## 10. Constraints & assumptions

- **No real PHI during development** — synthetic + de-identified data only (see CP03).
- Solo/small-team build cadence; each checkpoint must be independently valuable.
- Cloud: AWS primary, portable design.
- Frontier model use only under BAA with PHI minimization.

## 11. High-level risks (see `docs/threat-model-v0.md` and roadmap risk analysis)

- Extraction accuracy on the messy long tail → cascade + fine-tune + HITL.
- Policy RAG correctness → version-filtered retrieval + citation verification + refusal-when-unsure.
- Commoditization by frontier APIs → moat is the engineering around the model (eval, grounding, policy RAG, compliance).
- Time/scope for a solo build → checkpoint slicing.

## 12. Approval

This charter is approved as the basis for all subsequent checkpoints when signed off by the project owner. Changes are tracked via ADRs and version history.
