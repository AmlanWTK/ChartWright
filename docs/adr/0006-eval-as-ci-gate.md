# ADR-0006: Evaluation harness as a CI gate (model/prompt changes are tested like code)

- **Status:** Accepted
- **Date:** 2026-07-27
- **Deciders:** NahidHaque
- **Checkpoint:** CP01 (realized in CP26)
- **Reversibility:** Two-way door (mechanism can evolve; the principle is firm)

## Context

Model, prompt, and router changes can silently degrade accuracy, calibration, or hallucination rate — catastrophic in a clinical domain. Unit tests alone don't catch this because the risky behavior is statistical, not deterministic. We need reliability treated as infrastructure.

## Options considered

### Option A — Manual/ad-hoc evaluation before releases
- Pros: No upfront tooling.
- Cons: Inconsistent, unrepeatable, easy to skip; regressions ship silently; not defensible to buyers/auditors.

### Option B — Versioned gold sets + automated document-level eval that gates CI, plus production drift monitoring
- Pros: Every model/prompt/router change is measured against critical metrics (critical-field accuracy, hallucination rate, calibration/ECE, RAG citation-support, agent task-completion); regressions block merges; trends tracked over time; shadow eval + drift alerts in prod.
- Cons: Requires building and maintaining gold sets and a harness; eval runtime cost.

## Decision

Adopt **Option B**. A **document-level evaluation harness gates CI** — a change that regresses a critical metric beyond tolerance cannot merge — complemented by production drift monitoring, shadow evaluation, and human audit sampling. This is the single most important reliability practice in the project.

## Consequences

- **Positive:** Trustworthy, regression-safe AI; defensible metrics for interviews/buyers/auditors; the foundation for safe fine-tune promotion and model swaps.
- **Negative / trade-offs:** Upfront and ongoing investment in gold sets + harness; CI runtime; must guard against metric-gaming with complementary metrics + hard slices.
- **Follow-ups:** Build in CP26; grows from CP15 onward; gates fine-tune promotion in CP28; drift→retrain loop wired at CP34.

## Links

- FR-EVAL-* · NFR-ACC-* · `20-testing-strategy.md` · ADR-0002, ADR-0003
