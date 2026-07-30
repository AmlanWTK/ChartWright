# Threat Model v0 (CP01)

A first-pass STRIDE threat model and PHI data-classification map. This is intentionally an early, living document; it is deepened to v2 at CP29 (security hardening) with a penetration test.

## 1. Assets to protect

| Asset | Sensitivity | Notes |
|-------|-------------|-------|
| PHI in documents (member ID, diagnoses, clinical notes) | **Critical** | HIPAA-regulated |
| Extracted structured data | Critical | Derived PHI |
| Audit log | High | Integrity essential for compliance |
| Tenant configuration & credentials | High | Cross-tenant risk |
| Model weights / fine-tunes | Medium | IP + supply-chain integrity |
| Policy knowledge base | Medium | Correctness affects decisions |

## 2. Trust boundaries

- Internet ↔ edge (WAF/gateway).
- Control plane ↔ data plane.
- Platform ↔ external model providers (frontier APIs) — **PHI crossing point**, BAA-gated.
- Tenant ↔ tenant (logical isolation).
- Service ↔ data stores.

## 3. PHI data-flow classification (summary)

| Stage | PHI present? | Control |
|-------|-------------|---------|
| Ingestion / storage | Yes | Encryption (KMS), malware scan, per-tenant keys |
| Self-hosted OCR/VLM (Tier 0/1) | Yes | Stays in-boundary; network-isolated GPU nodes |
| Frontier escalation (Tier 2) | Yes (minimized) | BAA provider, minimization, no-train/no-retention |
| Logs / traces / metrics | **No** | Redaction enforced (CP06) |
| Event payloads (Kafka) | **No** | References/IDs only |
| Eval / training datasets | De-identified | De-id pipeline (CP27) |

## 4. STRIDE analysis (initial)

| Threat | Example | Control | Checkpoint |
|--------|---------|---------|------------|
| **Spoofing** | Stolen token, forged webhook | OIDC/mTLS, MFA, signed webhooks, short-lived JWT | CP07, CP21 |
| **Tampering** | Altered extraction or audit | Immutable append-only audit, object versioning, integrity hashes | CP08 |
| **Repudiation** | "I didn't approve that" | Audit with actor + correlation ID | CP08 |
| **Information disclosure** | Cross-tenant PHI leak | Postgres RLS, per-tenant KMS, network isolation, minimization | CP07, CP08 |
| **Denial of service** | Ingestion flood | WAF, rate limits, quotas, backpressure | CP07, CP21, CP30 |
| **Elevation of privilege** | Reviewer → admin | RBAC least-privilege, OPA admission | CP07 |
| **AI-specific: prompt injection** | Document text instructs the model/agent | Treat doc text as untrusted data; schema-constrained output; closed agent tool set | CP15, CP20 |
| **AI-specific: PHI leak to provider** | Naive frontier API call | Gateway BAA policy + minimization; default self-hosted | CP11 |
| **AI-specific: hallucination** | Fabricated member ID | Grounding contract + verifier + eval gate | CP12, CP15, CP26 |
| **Supply chain** | Tampered model weights / deps | Signed images, SBOM, pinned deps, weight checksums | CP02, CP28 |

## 5. Key early decisions driven by this model

- **PHI never in logs/traces/metrics or non-BAA prompts** — enforced in the service template (CP06) and gateway (CP11).
- **DB-enforced tenant isolation** (RLS), not app-level hope (CP08).
- **Document content is data, never instructions** — architectural stance for extraction + agent (CP15, CP20).
- **Default to self-hosted tiers for PHI**; frontier only under BAA with minimization (CP11).

## 6. Open questions for v2 (CP29)

- Break-glass access procedure and audit.
- Formal HIPAA control-to-implementation mapping + evidence.
- Penetration test scope; tenant-isolation attack test.
- Provider data-processing agreements finalized.
