# ADR-0008: Model Gateway as an in-process library; Ollama as the local Tier-0 engine

- **Status:** Accepted
- **Date:** 2026-07-30
- **Deciders:** Project owner (provider choice), assistant (packaging)
- **Checkpoint:** CP11
- **Reversibility:** Two-way door (both decisions are behind stable interfaces)

## Context

CP11 requires the single choke point for model calls (ADR-0002). Two open questions:
(1) packaging — the plan sketched a standalone FastAPI/gRPC service; (2) the local
Tier-0 engine — the plan specified vLLM-served dots.ocr/Qwen3-VL, which requires an
NVIDIA GPU the development machine does not have, and frontier APIs require a paid key
the owner has not (yet) provisioned.

## Decisions

### 1. In-process library first (`chartwright-gateway`), not a network service

All workers are Python and colocated; a network hop adds latency, deployment surface,
and failure modes while delivering nothing the abstraction doesn't already give us. The
choke-point guarantee comes from the *interface* — every model call goes through
`ModelGateway.generate()` — not from HTTP. The FastAPI facade is added when a non-Python
consumer, per-tenant quota enforcement at the edge, or the cloud re-entry (pre-CP12 GPU
serving) requires it; the class API is designed so wrapping it is mechanical.

### 2. Ollama as the local Tier-0/Tier-1 engine (owner's choice)

Zero cost, CPU-capable, serves small vision models (default `moondream`; configurable via
`CHARTWRIGHT_OLLAMA_MODEL`). Accuracy will be modest — acceptable, because CP11–CP15
prove *mechanisms* (routing, caching, failover, grounding, extraction contracts) on
synthetic data; accuracy targets bind at CP17/CP26 where the eval harness measures
whatever engines are then available. Tier 2 (frontier) chains to a clearly-labeled mock
until an API key is configured; the adapter seam (`ModelProvider` protocol) is one class.

## Consequences

- **Positive:** AI core development proceeds today at $0; provider swaps are config +
  one adapter; cache/breaker/metering logic is engine-agnostic and fully unit-tested.
- **Negative / trade-offs:** Local extraction quality will lag the production design —
  eval numbers on Ollama models are NOT the numbers that matter for the NFRs; no
  process isolation between gateway and workers until the facade exists.
- **Follow-ups:** Add the frontier adapter when a key exists; revisit packaging at the
  ADR-0007 cloud re-entry point; production Tier-0 (vLLM + dots.ocr/Qwen3-VL) lands
  with GPU capacity at CP12-cloud.

## Links

- ADR-0002 (gateway/cascade) · ADR-0007 (local-first + config-over-assumptions) ·
  `libs/chartwright-gateway/`
