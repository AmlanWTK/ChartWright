# ADR-0005: Bounded, tool-limited agent (not an open-ended autonomous agent)

- **Status:** Accepted
- **Date:** 2026-07-27
- **Deciders:** NahidHaque
- **Checkpoint:** CP01 (realized in CP20)
- **Reversibility:** Two-way door (agent design can evolve)

## Context

Prior-auth assembly is genuinely multi-step and conditional (is PA required? look up codes, check eligibility, gather evidence, is info missing? assemble packet). Hard-coding every branch is brittle; an agent handles the conditional logic. But this is a regulated, high-stakes, PHI environment where open-ended autonomy is unsafe (prompt injection via document content, non-determinism, liability for wrong decisions).

## Options considered

### Option A — Open-ended agent with broad tools (web, filesystem, arbitrary code)
- Pros: Maximum flexibility.
- Cons: Unsafe attack surface (document text could hijack it); non-deterministic; hard to audit; unacceptable liability for autonomous consequential actions.

### Option B — Hard-coded state machine, no agent
- Pros: Fully deterministic and auditable.
- Cons: Brittle across the long tail of conditional PA paths; high maintenance; poor at ambiguity.

### Option C — Bounded agent: closed tool set, step budget, full trace, durable HITL waits, low temperature
- Pros: Handles conditional logic while staying safe, deterministic-enough, replayable, and auditable; document text is treated as untrusted data, never instructions; never issues autonomous final denials.
- Cons: Requires careful tool design and guardrails; some engineering to make runs reproducible.

## Decision

Adopt **Option C**. The agent uses a **closed tool set** (`policy_search`, `code_lookup`, `eligibility_check`, `extract_field`, `fhir_build`, `request_human_input`), a step budget, low temperature, and a full logged trace. It pauses for humans via durable Temporal signals and **never makes a final coverage/clinical decision autonomously** — it drafts and recommends; a human or the payer's rules engine decides.

## Consequences

- **Positive:** Capability with safety, auditability, determinism, and injection resistance; clear liability boundary.
- **Negative / trade-offs:** Less "magic" flexibility; new capabilities require deliberately adding bounded tools.
- **Follow-ups:** Implement in CP20 with scenario + prompt-injection tests; keep the no-autonomous-denial rule as a hard invariant.

## Links

- FR-AGT-* · charter §6 (non-goals) · `11-ai-pipeline-design.md` · ADR-0003
