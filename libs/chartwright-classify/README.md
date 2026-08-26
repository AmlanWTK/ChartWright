# chartwright-classify (CP14)

Document classification: assigns exactly one `DocType` (from the 9-type taxonomy fixed
at CP03 — `chartwright_schemas.taxonomy`) to a packet, using the CP11 model gateway's
Tier-0 engine. This is the **first model-calling checkpoint** in the pipeline — CP12's
OCR and CP13's preprocessing are both deterministic, no model calls.

Classification runs at the `CLASSIFIED` stage, *before* OCR
(`STATUS_ORDER`: `NORMALIZED -> CLASSIFIED -> OCR_DONE`), so it works from the page
image alone — no OCR text is available yet.

## How it works: describe-then-map

The model is asked to **describe the page in free text**. A deterministic keyword mapper
turns that description into one `DocType`. **The model does perception; code owns the
ontology.**

This is not the obvious design, and the obvious design was measured first. Asking the
model to name one of the nine codes directly, with Ollama's structured-output mode
constraining decoding to a nine-value enum, scored **28.3%** — every miss returning
`clinical_note` at a confidence pinned between 0.66 and 0.71. The cause was not vision,
resolution or legibility, all of which were ruled out by experiment: asked simply to
describe the same PA form it had just mislabelled, the model replied *"a page of text
that appears to be a request for prior authorization"*. The 158-token enumerated prompt
was collapsing a 1.6B model to two tokens of garbage, and grammar-constrained decoding
was dressing that garbage in valid JSON.

**The general lesson, which CP15 inherits:** constrained decoding guarantees a
schema-*valid* response. It says nothing about whether the content means anything, and it
makes the failure invisible at the API boundary. See ADR-0010 and
`docs/CP14-document-classification.md` for the full measurement trail.

## API

```python
from chartwright_classify import classify_packet
from chartwright_gateway import build_default_gateway

result = classify_packet(page_image, gateway=build_default_gateway(), tenant_id="t")
# -> ClassificationResult(doc_type=DocType.PRIOR_AUTH_REQUEST, confidence=1.0,
#                         raw_text="The image shows a page of text that appears to be...")
```

`classify_packet` never raises on model output. An empty, truncated or nonsensical
description simply matches no keyword and returns `DocType.OTHER` with
`confidence=0.0` — exactly the case `ALWAYS_REVIEW_TYPES` and mandatory human review
exist for (`docs/domain/taxonomy.md`, "safety rails in the taxonomy itself"). Provider
failures (`AllProvidersFailedError`) *do* propagate: a dead engine is not the same thing
as an unrecognized document, and the pipeline's retry/DLQ machinery needs to see it.

`raw_text` holds the model's full description. This is strictly richer for audit than the
bare enum value the first implementation stored — a reviewer can see *why* a page was
typed the way it was, and a wrong call is legible rather than opaque.

## Confidence

Derived from evidence, not self-reported: the winning type's keyword score over the total
matched score. An unambiguous description scores 1.0; one naming two types scores lower;
no match is 0.0. Measured spread across the eval set: 0.00–1.00.

**It is still UNCALIBRATED. Do not use it for routing decisions before CP17.** But it is
at least a *signal* — the first implementation's model-self-reported confidence sat in a
dead 0.66–0.71 band regardless of input, which would have handed CP17 a constant to
calibrate.

## Evaluation (CP14 gate)

```bash
uv run python scripts/eval_classify.py --count 20
```

| Type | Accuracy |
|------|----------|
| `prior_auth_request` | 100.0% |
| `insurance_card` | 100.0% |
| `lab_report` | 95.0% |
| **Overall** | **98.3%** (gate ≥ 85%) |

The single miss is a hallucinated description — *"the text appears to be in a foreign
language"* — correctly routed to `OTHER` at 0.0. That is the safety net working.

**Read that number with the caveat it deserves:** three keyword phrases were added after
observing which documents failed. Each is standard clinical vocabulary a domain expert
would list a priori, but the table *was* revised against the eval set, so 98.3% measures
the mechanism on 60 synthetic images rather than generalization. CP26's versioned gold set
is where this gets tested for real.

## Known limitations (v1)

- **First-page-only input.** A packet whose defining content is on page 2+ (an insurance
  card's back, say) can misclassify.
- **Confidence is uncalibrated** — CP17's job, not this one.
- **Multi-packet documents:** classified using the first packet only. Fanning one upload
  out into N independently-routed documents is deferred to CP15/CP16.
- **The prompt is load-bearing.** `"Describe this image."` scores 98.3%; `"What kind of
  document is this?"` scored **0.0%** on every type. `_DESCRIBE_PROMPT` is not a free
  parameter — changing it requires re-running the eval.
- **The keyword table is brittle by construction.** It works because the taxonomy is nine
  coarse, verbally distinct types. It has not been measured against real faxes and would
  not survive a fine-grained taxonomy.
- **Three of nine types have synthetic generators**, so the gate covers three.
- No `ReviewTask` is opened for `ALWAYS_REVIEW_TYPES` or low confidence — CP14 only
  records the classification. Routing on it is CP17's escalation cascade.
