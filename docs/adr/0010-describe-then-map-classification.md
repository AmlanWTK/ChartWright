# ADR-0010: Classify by describe-then-map, not by constrained model selection

- **Status:** Accepted
- **Date:** 2026-08-26
- **Deciders:** Project owner (method choice), assistant (diagnosis and implementation)
- **Checkpoint:** CP14
- **Reversibility:** Two-way door (both sides sit behind `classify_packet`'s signature)

## Context

CP14 must assign one of nine `DocType` values (CP03 taxonomy) to a page image, using the
Tier-0 engine through the CP11 gateway (ADR-0002/0008). The obvious implementation — ask
the model to name the type, and constrain decoding to the nine valid codes so it cannot
invent a tenth — was built first and measured at **28.3%** against an 85% gate, with
every miss returning `clinical_note` at a confidence pinned between 0.66 and 0.71.

Diagnosis (full detail in `docs/CP14-document-classification.md`) established:

- The model **can** read the documents. Asked only "Describe this image.", moondream
  returned "a page of text that appears to be a request for prior authorization" for a PA
  form it had classified as `clinical_note`. Resolution, legibility and vision were all
  ruled out by direct experiment.
- The **constrained nine-way selection** is where it collapses. Given the 158-token
  enumerated prompt as free text, the model emitted two tokens of garbage (`'ids'`).
  Grammar-constrained decoding then guarantees *well-formed* output, which masks the fact
  that the content is meaningless — the failure is invisible at the API boundary.
- Prompt shortening alone did not fix it (33–53% across variants).

The generalizable problem: a 1.6B vision-language model is good at describing what it
sees and bad at multi-way constrained selection, and constrained decoding hides the
difference by always producing a schema-valid answer.

## Options considered

### Option A — Constrained selection (the first implementation)
- Pros: one model call; output is schema-valid by construction; the taxonomy lives in one
  place; trivially portable to a stronger model later.
- Cons: measured 28.3%; the grammar manufactures confident-looking answers from a model
  that has been derailed, so failures are silent; the model's self-reported confidence was
  a constant, leaving CP17 nothing to calibrate.

### Option B — Reorder the pipeline: OCR first, classify from text
- Pros: almost certainly the most accurate and most robust option; CP12's RapidOCR is
  deterministic, CPU-cheap and already built; text classification is a solved problem.
- Cons: changes `STATUS_ORDER` and the Temporal workflow shape; rewrites CP14's approved
  scope mid-checkpoint; makes every classification pay OCR cost even when a cheap visual
  signal would do. Deferred, not rejected — see Follow-ups.

### Option C — Describe-then-map (chosen)
- Pros: uses the model in the register it is measurably good at; the taxonomy mapping is
  pure, deterministic, unit-testable code that **cannot** hallucinate a type; the raw
  description is retained, so a reviewer can see *why* a page was typed; confidence can be
  derived from evidence rather than self-reported; measured 98.3%.
- Cons: two failure surfaces instead of one (model phrasing, and keyword coverage); the
  keyword table is brittle and taxonomy-specific; accuracy depends on an English prompt
  that cannot be tuned freely.

### Option D — A larger local model
- Pros: one config change (`CHARTWRIGHT_OLLAMA_MODEL`); no code.
- Cons: sidesteps rather than answers the design question; slower on CPU; the same
  constrained-selection failure mode would likely persist, just less often.

## Decision

Adopt **Option C**. The Tier-0 model produces a free-text description of the page; a
deterministic mapper in `chartwright-classify` scores that description against a
phrase→weight table and returns exactly one `DocType`. **The model does perception; code
owns the ontology.**

No keyword match yields `DocType.OTHER` at confidence 0.0 — never a guess. `OTHER` is in
`ALWAYS_REVIEW_TYPES`, so an unreadable page routes to a human.

## Consequences

- **Positive:** 28.3% → 98.3% on the synthetic gate. The taxonomy boundary is enforced by
  code, not by a grammar the model may be ignoring. Failures are legible — the description
  that produced them is stored. Confidence varies with evidence (measured 0.00–1.00)
  instead of sitting in a dead band, which gives CP17 something real to calibrate. Failure
  mode improved more than accuracy did: the old classifier was confidently wrong
  (`clinical_note` @ 0.66), the new one says "I don't know" and escalates.
- **Negative / trade-offs:**
  - **The prompt is load-bearing and not a free parameter.** `"Describe this image."`
    scores 98.3%; `"What kind of document is this?"` scored 0.0% on every type. Any change
    requires re-running the eval.
  - **The keyword table is brittle by construction.** It works because the taxonomy is
    nine coarse, verbally distinct types; it would not survive a fine-grained one, and it
    has never been measured against real faxes.
  - **The measured accuracy is fitted.** Three phrases were added after observing which
    documents failed. Each is defensible a priori, but the number is optimistic.
  - **Not uniformly better.** `lab_report` regressed from 80% (constrained) to 65% before
    the vocabulary fix. This approach won decisively on prior-auth forms, not everywhere.
  - Two failure surfaces to maintain instead of one.
- **Follow-ups:**
  - CP15 uses the same gateway for schema-constrained extraction. The failure mode
    documented here — grammar guarantees well-formed output while the content is
    meaningless — applies directly. Do not treat schema-valid extraction output as
    evidence of correct extraction; verify against CP12's `verify_at` grounding check.
  - Revisit **Option B** when CP15/CP16 need per-packet routing or when OCR runs before
    classification for other reasons. Classification from OCR text would remove both of
    this decision's brittleness sources at once.
  - CP26's versioned gold set is where the keyword table's generalization gets tested. If
    it fails there, Option B is the fallback, not more keywords.
  - `ModelRequest.response_format` now has no consumer. Retained for CP15's structured
    extraction; comment updated to stop naming the classifier.

## Links

- ADR-0002 (gateway/cascade) · ADR-0003 (grounding) · ADR-0008 (Ollama as local Tier-0)
- `docs/CP14-document-classification.md` (full measurement trail)
- `libs/chartwright-classify/` · `scripts/eval_classify.py`
