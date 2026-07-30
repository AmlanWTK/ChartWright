# ADR-0002: Cost-aware Model Gateway with a routing cascade (not direct model calls)

- **Status:** Accepted
- **Date:** 2026-07-27
- **Deciders:** NahidHaque
- **Checkpoint:** CP01 (realized in CP11, CP12, CP17)
- **Reversibility:** One-way door (foundational to COGS and portability)

## Context

OCR/understanding accuracy and cost vary enormously across models and pages. Frontier multimodal APIs read the hardest faxes but are expensive and rate-limited; strong open-weight OCR VLMs (dots.ocr, Qwen3-VL) run cheaply self-hosted and handle the clean majority. We must control per-page cost (the primary COGS lever), avoid provider lock-in, keep PHI on self-hosted tiers by default, and meter usage per tenant.

## Options considered

### Option A — Call one frontier API for everything
- Pros: Simplest; best single-model accuracy.
- Cons: Economically ruinous at millions of pages; latency; rate limits; provider lock-in; PHI leaves our boundary for every page; no regression safety.

### Option B — Single self-hosted model for everything
- Pros: Cheap; PHI stays in-house.
- Cons: Accuracy plateaus on the hard long tail (handwriting, degraded faxes, complex tables); no escalation path.

### Option C — Model Gateway with a cost-aware cascade (Tier-0 self-host → Tier-1 fine-tune → Tier-2 frontier)
- Pros: Cheapest-capable model per page; ≥70% served by cheap tiers; escalate only the hard minority; provider abstraction + caching + metering + PHI governance in one place; enables a learned router later.
- Cons: More engineering; requires calibrated confidence to drive escalation.

## Decision

Adopt **Option C**: a dedicated **Model Gateway** is the single choke point for all model calls, applying a cost-aware routing cascade. Calibrated confidence (ADR-0003) drives escalation. No service calls a model SDK directly.

## Consequences

- **Positive:** COGS control (the biggest economic lever); provider portability; centralized caching, metering, BAA/PHI governance, and observability; a clean seam to add a learned router.
- **Negative / trade-offs:** The gateway is a critical dependency (needs circuit breakers, failover); routing quality depends on good confidence calibration.
- **Follow-ups:** Build gateway in CP11; Tier-0 serving + grounding in CP12; calibration + cascade in CP17; fine-tuned Tier-1 in CP28.

## Links

- NFR-COST-*, NFR-ACC-* · ADR-0003 (grounding) · `12-ocr-vlm-pipeline.md`
