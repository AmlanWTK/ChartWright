# CP14 — Document Classification

- **Status:** ✅ Done — measured 98.3% against a 85% gate (see Verification)
- **Depends on:** CP13 (preprocessing, normalization & packet splitting) ✅
- **Feeds:** CP15 (structured extraction), CP16 (validation), CP17 (confidence calibration)
- **Owns pipeline stage:** `CLASSIFIED` (`STATUS_ORDER[2]`, between `NORMALIZED` and `OCR_DONE`)

## Objective

CP13 turns a raw upload into one or more normalized page-sequence packets, but says
nothing about *what* each packet is. CP14 assigns exactly one `DocType` (from the
9-type taxonomy fixed at CP03 — `libs/chartwright-schemas/src/chartwright_schemas/taxonomy.py`)
to each packet, using the CP11 model gateway's Tier-0 engine. This is the first
checkpoint that calls a model — everything in CP12/CP13 was deterministic.

Classification runs **before** OCR (`STATUS_ORDER`: `NORMALIZED -> CLASSIFIED ->
OCR_DONE`), so it works from the page image alone, not OCR text. It does not extract
fields (CP15), validate them (CP16), or calibrate confidence (CP17) — it only answers
"what kind of document is this."

## What was built

### 1. Classifier: image → DocType, by describe-then-map

`libs/chartwright-classify`. `classify_packet(page_image, *, gateway, tenant_id) ->
ClassificationResult`, where `ClassificationResult` carries `doc_type: DocType`,
`confidence: float`, and `raw_text` (the model's description) for audit.

The model is asked to **describe the page in free text**; a deterministic keyword
mapper (`map_description`) turns that description into exactly one `DocType`. The model
does perception; code owns the ontology. See **ADR-0010** for the decision and
**Verification** below for why the obvious alternative — asking the model to pick a type
directly — was measured and abandoned.

- **Input:** the packet's **first page only** (approved scope — see Decisions below).
- **Call shape:** `ModelRequest(prompt="Describe this image.", images=(page_png,),
  tier=0, purpose="classify", tenant_id=..., temperature=0.0, max_tokens=96)` through
  `ModelGateway.generate()` (CP11) — Tier-0 Ollama (`moondream`) locally.
- **Mapping:** phrase→weight table per type, scored by substring match on the lowercased
  description. Multi-word phrases outweigh single words ("insurance card" beats a bare
  "insurance"). Highest total score wins, with a deterministic tie-break on the type code.
- **No match is not an error:** it maps to `DocType.OTHER` with `confidence=0.0` and the
  description preserved. `OTHER` is in `ALWAYS_REVIEW_TYPES`, so an unreadable page
  routes to a human instead of being silently mistyped.

### 2. Confidence: derived from evidence, still explicitly uncalibrated

Confidence is the winning type's score over the total matched score — 1.0 when the
description is unambiguous, lower when it names more than one type, 0.0 when nothing
matched. Stored as-is in `Document.doc_type_confidence` (column already exists, CP08 —
no schema change).

It is **not calibrated** and must not drive routing before CP17. But it is a *signal*:
the first implementation's model-self-reported confidence sat in a dead 0.66–0.71 band
regardless of input, which would have given CP17 a constant to calibrate. The derived
score varies with the evidence, measured 0.00–1.00 across the eval set.

### 3. Pipeline integration

The `CLASSIFIED` stage in `services/pipeline/src/pipeline/activities.py` loads the
document's first normalized page from `chartwright-storage`, classifies it, and persists
`doc_type` + `doc_type_confidence` via `DocumentRepository.record_classification()`
(audited, same pattern as CP13's `record_normalized_pages`). Idempotency (ADR-0001)
holds: re-running an already-`CLASSIFIED` document is a no-op. A missing normalized
first page raises — that is a bug upstream, not a classification failure.

### 4. Synthetic documents for the eval

`chartwright-synthdata` gained `generate_insurance_card` and `generate_lab_report`
(CP03's generator covered only `prior_auth_request`). Three of the taxonomy's nine types
have generators; that partial coverage is stated, not silently assumed away.

### Explicitly out of scope (belongs to later checkpoints)
- Structured field extraction — CP15. Validation — CP16. Real calibration and the
  escalation cascade — CP17.
- Fan-out of one upload into N independently-routed `Document`s for multi-packet uploads
  — deferred again (see "Known limitations").
- Opening `ReviewTask` rows for `ALWAYS_REVIEW_TYPES` / low confidence — CP17's job.
  CP14 only *records* the classification.

## Decisions (approved by owner)

1. **Classification input:** first page of the packet only. Known v1 limitation: a packet
   whose defining content is on page 2+ could misclassify.
2. **Classification method:** describe-then-map rather than constrained selection, adopted
   after the first approach was measured at 28.3%. See ADR-0010.
3. **Keyword-table revision:** three phrases were added *after* observing eval failures
   (see Verification). Approved on the grounds that each is a term a clinician would list
   a priori; recorded here because it makes the final number optimistic.

## Verification

The honest version of what happened, because the failures are more instructive than the
final number.

### First implementation: 28.3%

Constrained selection — the model was given all nine type codes in the prompt and
Ollama's structured-output mode constrained decoding to a nine-value enum.

| Type | Accuracy |
|------|----------|
| `prior_auth_request` | 5.0% |
| `insurance_card` | 0.0% |
| `lab_report` | 80.0% |
| **Overall** | **28.3% FAIL** |

Every single miss returned `clinical_note`, with confidence wedged between 0.66 and 0.71.

### Two hypotheses, both wrong

- **Enum positional prior.** `sorted(_KNOWN_TYPES)` puts `clinical_note` first
  alphabetically, which matched the failure exactly. Reverse-sorting the enum produced
  **byte-identical** output. Dead. (The test was also weaker than it looked: GBNF
  alternation order does not change the model's logits, so identical output was the
  expected result under either hypothesis.)
- **Encoder resolution.** Pages render at 1700×2200 and moondream's vision encoder
  resizes to roughly 378×378, which would turn a 46pt title into ~8px. Asking the model
  to read the heading returned empty at full page, at a 12% band, *and* at a tight crop.
  Dead.

### What the raw probe showed

Bypassing the gateway and printing full Ollama response bodies isolated it in five calls:

| Case | Prompt | Result | `eval_count` |
|------|--------|--------|--------------|
| A | text only, no image | `''` | 1 |
| B | billboard image, "Describe this image." | reads the text correctly | 37 |
| C | **real PA page, "Describe this image."** | **"a request for prior authorization"** | 64 |
| D | real PA page, the 158-token classify prompt | `'ids'` | **2** |
| E | D + a 3-value grammar | correct | 22 |

Case C is the finding: **the model reads the document correctly in free text.** Vision,
resolution and legibility were never the problem. Case D is the cause: a 158-token
enumerated prompt collapses a 1.6B model to two tokens of garbage. Case A is moondream
being vision-only — a red herring, and the source of a latent test bug (see below).

Prompt length alone did not explain it either: shortening the prompt while keeping
constrained selection scored 33–53%, rescuing `insurance_card` but not `prior_auth_request`.

### Describe-then-map: 83.3%

| Type | Constrained | Describe-then-map |
|------|-------------|-------------------|
| `prior_auth_request` | 5% | **100%** |
| `insurance_card` | 0% | **85%** |
| `lab_report` | 80% | **65%** |
| **Overall** | 28.3% | **83.3% FAIL** |

Not a uniform win. `lab_report` **regressed** — constrained decoding was genuinely better
on the one type whose geometry survives everything. Recorded because presenting
describe-then-map as strictly superior would be false.

Two generator bugs surfaced along the way, both found by *reading the model's
descriptions rather than the scores*:

- `generate_insurance_card` drew a bordered block on a letter-size portrait page, ~85%
  blank. The model described it as *"a blank white page … the page is empty"* — an
  accurate description of a bad image. Rewritten as a landscape CR80 card that fills the
  frame. **0% → 85%.**
- Nobody had ever looked at these images. They were written during CP14 and judged only
  through a 1.6B model's opinion of them. The eval was measuring the generator.

### Vocabulary gap: 98.3%

Every remaining miss was `other` at 0.00 — descriptions matching no keyword. Reading them
showed the model saying **"lab result"** / `"Lab Results"` (the table knew only
"laboratory result" and "lab report") and **"Acme Health Plan card"** (the table knew only
"insurance card"). Three phrases added: `lab result` (4.5), `health plan card` (4.5),
`health insurance` (2.0).

| Type | Accuracy |
|------|----------|
| `prior_auth_request` | 100.0% (20/20) |
| `insurance_card` | 100.0% (20/20) |
| `lab_report` | 95.0% (19/20) |
| **Overall** | **98.3% PASS** (target ≥ 85%) |

The single miss (`lab_report`, seed 42010) is a hallucinated description — *"likely a
form or list … the text appears to be in a foreign language"* — correctly routed to
`other` at 0.00 confidence. That is the safety net working, not a defect.

**This number is fitted.** The keyword table was revised after seeing which documents
failed. Each phrase is defensible without the failure data, but the honest reading is
that 98.3% measures the mechanism on 60 synthetic images, not generalization. CP26's
versioned gold set is where this gets tested for real.

### Commands

```bash
uv run python scripts/eval_classify.py --count 20   # 98.3% PASS
uv run pytest --cov --cov-report=term-missing        # 85.17% total; classifier.py 100%
uv run ruff check . && uv run ruff format --check . && uv run mypy
```

## Success criteria / gates
- ✅ Classification accuracy ≥ 85% on synthetic documents — **measured 98.3%** (fitted;
  see caveat above).
- ✅ Unrecognizable descriptions always map to `OTHER` + confidence 0.0, never raise —
  covered by adversarial unit tests (empty, whitespace, `'ids'`, garbage, a type name
  outside the nine, 4000 chars).
- ✅ Idempotent: re-classifying an already-`CLASSIFIED` document is a no-op.
- ✅ All existing tests remain green; coverage gate (≥ 80%) holds at 85.17%.

## Definition of Done
Universal DoD applies in full. This is an AI checkpoint — eval gate defined and measured,
model calls go only through the CP11 gateway (no direct provider calls), no PHI in
prompts or logs (synthetic data only).

## Known limitations (v1)
- **First-page-only input.** A packet whose defining content is on page 2+ can misclassify.
- **Confidence is uncalibrated.** Do not route on it before CP17.
- **Multi-packet documents:** classified using the first packet only. The fan-out of one
  upload into N independently-routed documents is now deferred **twice** (CP13 → CP14 →
  CP15/CP16). CP15 extracts per document type and will need it; budget for it there
  rather than deferring a third time.
- **The prompt is load-bearing.** `"Describe this image."` scores 98.3%; `"What kind of
  document is this?"` scored **0.0%** on every type. Changing `_DESCRIBE_PROMPT` requires
  re-running the eval.
- **The keyword table is brittle by construction.** It works because the taxonomy is nine
  coarse, verbally distinct types. It has not been measured against real faxes and would
  not survive a fine-grained taxonomy.
- **Six of nine types have no synthetic generator**, so the gate covers three.

## Findings that outlive this checkpoint

Two process problems surfaced here that are not CP14-specific and should be fixed before
they cost more:

1. **An eval can measure its own scaffolding.** `insurance_card` scored 0% because the
   generator drew a blank page — invisible for as long as nobody looked at the images.
   Any generator feeding a gate should be visually inspected once by a human, and the
   eval should print what the model actually said, not only whether it was right.
2. **A skipped integration test satisfied a DoD clause while proving nothing.**
   `TestOllamaLive::test_generate_text_via_local_model` asserted non-empty text from a
   text-only prompt to a vision-only model. It was wrong from the day it was written and
   never ran, because Ollama was not installed on the dev machine until CP14 — so CP11
   closed with its only live-provider test skipping silently. CP12's and CP13's
   integration suites are in the same position whenever the local stack is down (17 tests
   skipped in the CP14 verification run). Recommend a CI/verification flag that **fails**
   rather than skips when a required dependency is missing, so a checkpoint cannot close
   on a green run whose integration tests never executed.

## Execution log

- Owner approved the original draft spec (first-page-only input, self-reported confidence)
  via two scoped questions before implementation began.
- First implementation built and merged into the working tree: constrained nine-value
  grammar, strict JSON parser, `OTHER`-on-failure fallback, `record_classification()`,
  `CLASSIFIED` stage wiring, `scripts/eval_classify.py`, `generate_insurance_card` /
  `generate_lab_report`. Verified in the implementation sandbox as ruff/mypy/pytest clean,
  but **the eval gate and integration suite were never run** — flagged as pending.
- First live run of the gate: **28.3% FAIL**.
- Diagnosis (see Verification): two hypotheses tested and discarded, raw-provider probe
  isolated the cause, prompt-length grid and a four-strategy comparison measured the
  alternatives.
- Owner chose describe-then-map from four options (vs. reordering the pipeline to classify
  from OCR text, accepting the failure, or trying a larger local model). → **83.3%**.
- Owner approved three keyword additions after reviewing the failing descriptions, on the
  basis that each is standard clinical vocabulary. → **98.3% PASS**.
- Two pre-existing test defects fixed: the CP14 wiring test still scripted the removed JSON
  contract, and CP11's live-Ollama test had never executed (see Findings).
- ADR-0010 records the describe-then-map decision.
