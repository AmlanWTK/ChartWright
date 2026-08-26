# ADR-0011: Extraction's cheapest tier uses no model at all

- **Status:** Accepted
- **Date:** 2026-08-26
- **Deciders:** Project owner (method choice), assistant (spike design and implementation)
- **Checkpoint:** CP15
- **Reversibility:** Two-way door (behind `extract_document`'s signature)

## Context

CP15 must pull the fields declared in a `DocSchema` off a page image, each grounded per
ADR-0003. The approved design was: the Tier-0 VLM proposes a value per field, and
`locate_value` grounds it against CP12's OCR tokens — the same "model perceives, code owns
structure" split that rescued CP14 (ADR-0010).

Learning from CP14 — where the checkpoint was built first and measured second — CP15
opened with a capability spike **before** any implementation. Three reading paths, six
synthetic PA documents, four representative fields, 48 model calls:

| Arm | Answered | Grounded | Correct |
|-----|----------|----------|---------|
| A. VLM, question prompt | 9/24 | **0/24** | **0/24** |
| B. VLM, bare label prompt | 12/24 | **0/24** | **0/24** |
| C. OCR label anchor, **no model** | 24/24 | **24/24** | **23/24** |

Both VLM arms produced zero groundable output, emitting things like
`urn:ietf:params:member:urn:ietf:members:...` and `ids/23/0` — the same `ids` token CP14's
raw probe got from a question-style prompt. moondream describes images; it does not answer
questions about them, and per-field extraction is inherently question-form.

Arm C was included as a control precisely because the reading path had been chosen from a
description of the options rather than from evidence.

## Decision

**Extract deterministically by label anchoring.** Locate the printed label
(`FieldSpec.label`) in the OCR tokens by fuzzy window match; read the run of tokens to its
right, or on the line below when nothing is to the right; emit a `GroundedField` whose
bbox is the envelope of those value tokens. A label that cannot be found, or that carries
no value tokens, yields **no field** — never a guess.

**No model participates in extraction.** VLM escalation for unfound fields is deferred to
CP17, whose stated scope is the escalation cascade.

## Consequences

- **Positive:** 0/24 → 23/24 on the spike's fields. Extraction becomes deterministic,
  free, fast, and fully testable without a model or a network — the unit suite builds
  `PageOcr` fixtures by hand and runs in milliseconds. Grounding is exact by construction
  rather than recovered by fuzzy search, because the bbox *is* the value tokens' envelope.
- **This is the cascade's bottom rung, not a departure from it.** ADR-0002 routes each page
  to the cheapest thing that can handle it. Free-and-deterministic is cheaper than Tier-0,
  so a cost-aware cascade should prefer it wherever it works and escalate where it does
  not. CP17 owns that escalation decision, which is exactly where it belongs.
- **Negative / trade-offs:**
  - **Brittle in the way synthetic data hides.** The anchor needs a readable printed label
    and a regular label:value geometry. Skew, wrapped values, multi-column layouts and
    checkbox fields all break it, and none appear in the clean slice. The degraded-slice
    numbers are the early warning; CP27's de-identified real documents are the real test.
  - **OCR misrecognition passes straight through, grounded and plausible.** The spike's one
    miss was `Drew Iyer` → `Drew lyer`: correctly located, confidently wrong. Grounding
    proves *where*, never *what was actually read*. A grounded field is not a verified
    field — CP16 and CP17 are the defenses, and this must not be forgotten by anything
    downstream that sees provenance and infers correctness.
  - **`MIN_LABEL_SCORE = 0.75` is measured, not universal.** It separates the current
    schema's confusable pairs (`Member ID` vs `Member Name` score 0.70 against each other;
    exact labels score 1.00). A denser schema needs it re-measured.
  - CP15 becomes a non-model checkpoint for extraction, so the AI-checkpoint DoD applies
    only partially. Stated explicitly in the spec rather than quietly skipped.
- **Follow-ups:**
  - CP17 adds VLM escalation for fields the anchor misses, and calibrates the derived
    `label_score × token_confidence` signal.
  - If degraded-slice accuracy collapses, the answer is a better OCR engine or an
    escalation tier — not a lower threshold.
  - Revisit when GPU Tier-0 (vLLM + dots.ocr/Qwen3-VL) lands: a competent VLM may beat the
    anchor on irregular layouts, and this decision should be re-measured, not assumed.

## Links

- ADR-0002 (cost-aware cascade) · ADR-0003 (grounding contract) · ADR-0008 (local Tier-0)
- ADR-0010 (describe-then-map — the CP14 decision this spike's method learned from)
- `docs/CP15-structured-extraction.md` (Phase 0 measurement trail) · `libs/chartwright-extract/`
