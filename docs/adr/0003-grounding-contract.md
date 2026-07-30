# ADR-0003: Mandatory grounding contract (bbox + source span + calibrated confidence on every field)

- **Status:** Accepted
- **Date:** 2026-07-27
- **Deciders:** NahidHaque
- **Checkpoint:** CP01 (realized in CP12, CP15, CP17)
- **Reversibility:** One-way door (core trust guarantee)

## Context

In a clinical, high-stakes domain, a plausible-but-wrong value (e.g., a hallucinated member ID) causes real harm and denials. We must be able to (a) show a human exactly where each value came from, (b) triage uncertainty automatically, and (c) audit every output. Raw model generation provides none of these guarantees by default.

## Options considered

### Option A — Trust model text output as-is
- Pros: Simplest; least plumbing.
- Cons: No provenance, no calibrated uncertainty, no defense against hallucination; unacceptable for PHI/decisions.

### Option B — Grounding contract: every field carries page + bounding box + source span + calibrated confidence, verified against the OCR text at that location
- Pros: Auditability; enables confidence-driven HITL triage; a grounding verifier catches fabricated values; makes the review UI's bidirectional linking possible; doubles as a security control.
- Cons: More schema + a verification pass; requires confidence calibration to be meaningful.

## Decision

Adopt **Option B**. The grounding contract is **mandatory** — no extracted field ships without provenance and calibrated confidence, and a grounding verifier confirms each value appears at its claimed location. Hallucination is treated as a defect measured in the eval harness.

## Consequences

- **Positive:** Trust, auditability (HIPAA), automated uncertainty triage, anti-hallucination, and the foundation for the review console and cost-aware escalation.
- **Negative / trade-offs:** Additional per-field metadata and a verification step; confidence must be calibrated (ECE ≤ 0.05) to be actionable.
- **Follow-ups:** Contract defined with Tier-0 serving in CP12; enforced in extraction CP15; calibration in CP17; hallucination metric gated in CP26.

## Links

- FR-EXT-05, FR-EXT-06, NFR-ACC-03, NFR-ACC-05 · ADR-0002 · ADR-0006 · `11-ai-pipeline-design.md`
