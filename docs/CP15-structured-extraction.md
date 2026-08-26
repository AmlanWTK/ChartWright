# CP15 — Structured Extraction (grounded, schema-constrained)

- **Status:** 🟡 Approved, in progress. Phase 0 complete — reading path revised on measurement (see below).
- **Depends on:** CP14 (classification) ✅ · CP12 (OCR + grounding library) ✅ · CP08 (persistence) ✅
- **Feeds:** CP16 (validation & code systems), CP17 (calibration & cascade), CP22 (FHIR output), CP24 (review console)
- **Owns pipeline stage:** `EXTRACTED` (`STATUS_ORDER[4]`) — and wires `OCR_DONE` (`STATUS_ORDER[3]`), which CP12 left as a stub

## Objective

CP14 answers "what kind of document is this." CP15 answers "what does it say" — pulling
the fields declared in the document type's `DocSchema` off the page, each one carrying
mandatory provenance (page + bbox + source span) per ADR-0003.

This is the checkpoint the grounding contract was built for. `GroundedField` already
makes provenance structural at the Pydantic level: an extractor **physically cannot**
emit a field without a location. CP15 is where that constraint starts doing work.

## The design principle, earned at CP14

CP14 measured 28.3% because grammar-constrained decoding guarantees *schema-valid* output
while saying nothing about whether the content means anything. The failure was invisible
at the API boundary. CP15 faces the identical risk at higher stakes — a fabricated
`member_id` is worse than a mislabelled document — and answers it structurally:

> **The model proposes a value; `locate_value` must find that value in the OCR tokens, or
> the field is never emitted.** A hallucinated value has no pixels behind it, so it cannot
> be grounded, so it does not survive. The model reads; code decides what is real.

Same split that fixed CP14, with teeth this time: the anti-hallucination check is not a
prompt instruction the model may ignore, it is a lookup that either succeeds or doesn't.

## Phase 0 — capability spike ✅ COMPLETE

CP14's costliest mistake was building the checkpoint and *then* discovering the model
couldn't do the task. CP15 inverted that order: before writing any extractor, one spike
measured three reading paths on identical documents (6 synthetic PA forms, clean slice,
4 representative fields, 48 model calls).

| Arm | Answered | Grounded | Correct |
|-----|----------|----------|---------|
| A. VLM question — *"What is the {label} on this form?"* | 9/24 | **0/24** | **0/24** |
| B. VLM bare label — *"{label}:"* | 12/24 | **0/24** | **0/24** |
| C. OCR label anchor — **no model** | 24/24 | **24/24** | **23/24** |

Both VLM arms produced **zero groundable output**. What they produced instead:

```
urn:ietf:params:member:urn:ietf:members:urn:ietf:org:net:...
ids/23/0        ids/p/sa_1396        ids.
```

That `ids` token is the same output CP14's raw probe got from a question-style prompt.
moondream does not answer questions about images; it describes them. Per-field extraction
is inherently question-form, so this path could not work on this engine. Cost of finding
out: four minutes, versus CP14's rebuilt checkpoint.

**The one anchor miss matters more than the twenty-three hits.** `want='Drew Iyer'`,
`got='Drew lyer'` — capital I read as lowercase l. The anchor located the correct region;
RapidOCR misrecognized the glyph. This establishes a limit that must not be forgotten
downstream:

> **Grounding proves that text is at that location. It does not prove the text was read
> correctly.** ADR-0003 defends against fabrication, not against misrecognition. A
> grounded field is not a verified field. CP16 (validation) and CP17 (confidence) are the
> defenses against OCR error; provenance is not.

**Caveats on the 96%.** Clean slice only — `fax` and `bad_fax` are untested, and
degradation attacks exactly what the anchor depends on (reading the printed label). And
these are synthetic forms with perfectly regular label:value rows, produced by the same
code that defines the gold labels. This is close to the easiest possible case, and the
number should be read as "the mechanism works", not "extraction is solved".

## Scope

Three separable pieces, each independently verifiable. Recommend landing them as three
commits on one `cp15/structured-extraction` branch, reviewable in order.

### 1. Wire the `OCR_DONE` stage (completes CP12's pipeline integration)

CP12 built `libs/chartwright-ocr` and its eval but never connected it: `advance_stage`
dispatches only `NORMALIZED` and `CLASSIFIED`. CP15 is the first consumer, so it wires it.

- `_ocr_document(repo, tenant_id, doc)`: for each normalized page, load the image from
  `chartwright-storage`, run the `OcrEngine`, persist the `PageOcr` as JSON under a
  deterministic key (`tenants/{t}/documents/{d}/ocr/page-{n:04d}.json`), mirroring how
  CP13 stores normalized pages.
- **No schema change** — object storage, not a new table, same discipline as CP13/CP14.
- Idempotent: re-running an already-`OCR_DONE` document is a no-op.

### 2. Multi-packet fan-out (deferred at CP13, deferred at CP14, due here)

Extraction is per document type, so a multi-packet upload genuinely needs one `Document`
per packet — deferring a third time would build CP16 on the wrong assumption.

- Alembic migration adding `parent_document_id` and `packet_index` to `documents`. **This
  is the first schema change since CP08** — RLS policies and the audit trigger must be
  re-verified against the new column, not assumed.
- After `NORMALIZED`, a document whose packet split produced N > 1 packets spawns N-1
  sibling documents; the workflow processes each independently from `CLASSIFIED` onward.
- The parent retains the original upload and its object key; children reference the
  parent's pages by range.
- Single-packet uploads (the overwhelmingly common case) take an unchanged path.

### 3. The extractor — `libs/chartwright-extract`

`extract_document(pages, doc_type, document_id) -> ExtractionResult`

**No model calls, no gateway dependency.** For each `FieldSpec` in the type's `DocSchema`:

1. **Anchor** — locate the printed label (`FieldSpec.label`) in the page's OCR tokens by
   fuzzy window match, tolerant of OCR noise.
2. **Read the value** — take the run of tokens to the right of the label within its
   vertical band; fall back to the line below when nothing sits to the right (forms use
   both layouts).
3. **Emit** — `GroundedField(key, value_raw, confidence, provenance)`, where the bbox is
   the envelope of the value tokens and `source_span` is their literal text. A field whose
   label cannot be found, or which has no value tokens, is **absent** — never fabricated,
   per ADR-0003.

Confidence is derived from the anchor's label-match score and the engine's own token
confidences — explicitly **uncalibrated**, CP17's job, same posture as CP14.
`value_normalized` stays `None`; that is CP16's.

Persistence via CP08's existing `create_extraction` + `add_field`.

**This makes CP15 a non-AI checkpoint for extraction.** That is a feature, not a
compromise: ADR-0002's cascade routes each page to the cheapest thing that can handle it,
and free-and-deterministic is cheaper than Tier-0. The anchor is the cascade's bottom
rung, not a departure from it. Recorded in ADR-0011.

### Explicitly out of scope
- **Tables.** `PRIOR_AUTH_REQUEST` declares one `TableSpec` (`required=False`, so a
  fields-only `ExtractionResult` is valid). Table extraction is a different problem and
  `ExtractedTable` has no `add_table` repository method yet — CP16 or later.
- **Validation, normalization, code systems** (`value_normalized`, `code_system`) — CP16.
- **Calibration, ECE, escalation, tier cascade** — CP17. CP15 calls Tier-0 only.
- **`ReviewTask` creation** for low-confidence or missing critical fields — CP17.
- **The other four `STRUCTURED_TYPES`** — only `prior_auth_request` has labelled ground
  truth, so it is the only one that can be honestly measured.

## Decisions (approved by owner before drafting)

1. **`OCR_DONE` wired inside CP15**, labelled as completing CP12's integration rather than
   new scope, since CP15 is its first consumer.
2. **Reading path: VLM on the page image, grounded deterministically by `locate_value`.**
   The alternative — OCR text into a text model — is blocked on the current Tier-0 engine:
   moondream returns empty for any text-only prompt (measured, CP14 raw probe case A), so
   it would require a new local model and an ADR-0008 amendment.
3. **Type scope: `prior_auth_request` only.**
4. **Multi-packet fan-out: implemented here**, not deferred a third time.

## Success criteria / gates

CP14's gate conflated two things — whether the mechanism works, and whether a 1.6B model
is any good — and the checkpoint nearly closed on a misreading of it. With Phase 0 having
removed the model from the extraction path entirely, CP15's gates test our code, so they
can be strict. What they must NOT do is let a high synthetic number imply readiness.

**Correctness gates (strict):**
- **Hallucinated-field rate = 0%.** Not ≤0.5% — *zero*. A field with no anchor and no
  value tokens is never emitted, so any non-zero rate is a bug in our code.
- Every emitted `GroundedField` passes `verify_at` against its own provenance — the
  emitted bbox really does contain the emitted text.
- No emitted key outside the type's `DocSchema` (already enforced by `ExtractionResult`;
  asserted explicitly).
- Extraction is **deterministic**: same page, same result, byte-for-byte. Trivially true
  without a model, and worth a test so it stays true if one is ever added.
- Idempotent re-runs; all CP01–CP14 tests green; coverage ≥ 80%.

**Capability gates (per slice, never aggregated):**
- Field exact-match accuracy on the **clean** slice: **≥ 90%** (Phase 0 measured 96% on
  4 fields; the full 14-field schema will be harder — checkbox and free-text fields have
  no clean label:value row).
- Reported per field and per degradation slice (`clean` / `fax` / `bad_fax`). **The
  degraded slices carry no pass/fail bar in CP15** — they are a measurement of how much
  work CP17's escalation has to do, and a bad number there is information, not failure.
- Critical-field accuracy reported against the 95% NFR as a **gap measurement**, not
  pass/fail, per ADR-0008.
- **Missed-field rate is a headline metric, not a footnote.** With no model fallback, a
  field the anchor cannot find is simply absent; how often that happens is the single
  most important number for sizing CP17.

**What these gates deliberately do not claim:** that extraction works on real documents.
Synthetic forms have regular label:value rows generated by the same code that defines the
labels. Real faxes bring skew, wrapped values, multi-column layouts and missing labels.
CP26's gold set and CP27's de-identified real documents are where that claim gets earned.

## Deliverables
- `libs/chartwright-extract` — `extract_document`, per-field prompting, grounding-gated emission.
- `services/pipeline` — `OCR_DONE` and `EXTRACTED` stages wired; packet fan-out in the workflow.
- `libs/chartwright-db` — Alembic migration for `parent_document_id` / `packet_index`; RLS + audit re-verified.
- `scripts/eval_extract.py` — per-slice, per-field metrics against synthdata's labels.
- README + this spec updated with measured results; ADR if the spike changes the approach.

## Definition of Done
Universal DoD applies. This is an AI checkpoint: eval gate defined and measured, model
calls only through the CP11 gateway, no PHI (synthetic only). Infrastructure DoD applies
to the migration: rollback path tested (`make db-downgrade`), tenant-isolation test
re-run against the new column.

## Risks
- **Cost/latency:** one model call per field per page — 14+ calls per PA document, on CPU.
  Acceptable locally; noted for CP32 (FinOps) and CP30 (load).
- **Per-field prompting is unproven on this model.** Phase 0 exists to find out first.
- **The migration is the first since CP08.** RLS policies and audit triggers are the
  risk surface, not the column itself.
- **Fan-out changes the workflow shape**, which CP10's integration tests cover — expect
  those to need updating, and treat any that *don't* fail as suspicious.

## Process changes carried in from CP14
1. **Measure the model before building around it** (Phase 0). CP14 built, measured, rebuilt.
2. **Look at every synthetic document a gate depends on**, once, with human eyes.
   `generate_prior_auth` has been inspected this session; anything new must be too.
3. **Integration tests that skip must not count as passing.** CP11's live-Ollama test
   skipped through an entire checkpoint's DoD. If a verification flag lands, CP15 should
   run under it.

## Execution log
- (empty — awaiting approval)
