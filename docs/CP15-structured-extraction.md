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

## Measured results (extraction, `scripts/eval_extract.py --count 10`)

| slice | exact | fuzzy | missed | IoU | critical |
|-------|-------|-------|--------|-----|----------|
| clean | **98.5%** | 99.2% | 0.0% | 0.68 | **98.6%** |
| fax | 69.2% | 78.5% | 16.2% | 0.55 | 74.3% |
| bad_fax | **0.0%** | 0.0% | **100.0%** | 0.00 | 0.0% |

Mechanism gates all PASS: 0/255 self-verification failures, 0 off-schema keys, deterministic
re-run identical. Capability gate PASS at 98.5% against ≥ 90%.

Critical-field accuracy of 98.6% exceeds the 95% NFR, and means little yet: clean synthetic
forms whose labels come from the same code that defines the gold. CP26's gold set and CP27's
real documents are where that claim gets earned.

**`bad_fax` collapses completely** — 0% exact, 100% missed. Reported, not gated, per the gate
design. It is the number that sizes CP17: escalation must carry *every* badly-degraded
document, not a minority of them.

### The bug the gate nearly hid

`urgency` first measured 0% while reporting 0% missed — it returned `'Contact Phone:'`, the
*next field's printed label*, on all ten documents, **and passed self-verification**, because
that text genuinely is at that bbox. The overall figure was 90.8% and PASS. A field
fabricating 100% of the time was invisible in the aggregate; only per-field reporting showed
it.

**Root cause: two sources of truth had drifted.** The schema declared
`label="Urgency (Standard/Urgent)"` while the form printed `"Urgency:"`. `_find_label` then
matched the two-token window `['Urgency:', 'Standard']` at 0.82 — absorbing the *value* into
the label — so the value-reader started past it, found nothing on that line, dropped to the
row below and returned the next field's label. `FieldSpec.label` is documented as "the human
label as typically printed on forms"; no form prints its own permitted values. The schema was
wrong, not the anchor.

It took three wrong hypotheses to find (the collision guard was rejecting it; the clean slice
was not a no-op; the image mode differed), each argued from source and each killed by data.
Fixing `urgency` moved clean accuracy 90.8% → 98.5% and missed 7.7% → 0.0%.

Two defences came out of it, and the second matters more than the first:

1. **A label-collision guard** in `anchor_field` — a form value is never another field's
   printed label. This turned a grounded fabrication into an honest absence, which CP17 can
   escalate. It treats the symptom, and is worth keeping for the general case.
2. **`test_label_consistency_unit.py`** — asserts the generator's printed labels equal the
   schema's declared labels. This addresses the *class*: two sources of truth drifting with
   nothing checking they agree. **It found two more instances on its first run**
   (`diagnosis_code`, `procedure_code`, both missing the word "Code"), which were still
   working only because fuzzy matching absorbed the gap at 0.84.

### What grounding cannot defend against

Both remaining clean-slice failures are OCR glyph confusion that arrives grounded, verified,
and wrong:

- `Dr. Avery Iyer, MD` → `Dr. Avery lyer, MD` (capital I as lowercase l)
- `I25.10` → `125.10` (capital I as digit 1) — **a critical ICD-10 field**

`125.10` is not a valid ICD-10 code; the format is a letter followed by digits. It was
extracted, grounded, self-verified and silently corrupt. `verify_at` reported 0/255 failures
throughout, correctly: the text really was at that box. **Provenance proves location, never
recognition.**

These are concrete acceptance cases for CP16, not aspirations: a `FieldKind.ICD10` validator
rejects `125.10` on format alone, and a `FieldKind.TEXT` field whose value equals another
field's label is rejectable on content. Both of this checkpoint's silent-corruption modes are
catchable by validation and neither is catchable by grounding.

### Open at time of writing
- **`clinical_justification` is unmeasured** (`--`): the generator draws it but records no
  gold label, so the eval cannot see it. Same shape as CP14's insurance-card bug — an eval
  only measures what the generator admits to.
- **`REFERRAL` still declares `label="Diagnosis (ICD-10)"`.** Left deliberately: that type has
  no generator, so there is no evidence of what a referral form prints, and guessing is what
  caused this bug. When a referral generator lands, extend the consistency test to it and let
  the form decide.
- **Integration tests have never run against this wiring.** `OCR_DONE` and `EXTRACTED` are
  proven only against hand-built fakes; the CP10 lifecycle test skipped because Docker Hub
  could not be reached to pull Postgres/Kafka/Temporal. **CP15 cannot close until it runs.**
  This is CP14's own recorded finding — a skipped integration test satisfying a DoD clause
  while proving nothing — recurring one checkpoint later.
- **Multi-packet fan-out is not built.** Blocked on the same Docker outage, since it needs a
  migration plus CP08's tenant-isolation tests re-run against the new column.

## Closing the checkpoint (2026-09-02)

Everything under "Open at time of writing" is resolved or explicitly carried. That section
is left exactly as written — the trail is worth more than a tidy document, and two of its
entries turned out to be the most valuable things in it.

### Multi-packet fan-out — built, and it found a bug the tests could not

Migration 0003 makes the dedupe index partial (`WHERE parent_document_id IS NULL`) so
children can reuse the parent's `content_hash`. `create_child_document` / `list_children`
persist them; `_fan_out_packets` creates one child per packet with pages renumbered from 1.

Writing the database tests found a live defect: `create_document` looked up by
`content_hash` with `scalar_one_or_none()`, which raises `MultipleResultsFound` the moment
children share the parent's hash. **Resubmitting a multi-packet fax would have crashed
intake.** Scoped the query to `parent_document_id IS NULL`, matching the index.

Then reading `workflows.py` found a larger one, and this is the part worth remembering:
`_fan_out_packets` documented that *"the parent stops at NORMALIZED"* while
`DocumentPipelineWorkflow.run` was a flat loop that knew nothing about children. So the
parent — the upload, explicitly not a document to extract from — was classified, OCR'd,
extracted and driven to COMPLETED, while the children sat at NORMALIZED forever. **All 18
database and ingestion integration tests passed the entire time**, because the gap lived in
the workflow layer and nothing ran a workflow over a multi-packet document. A docstring
described behaviour that did not exist, and no test disagreed.

ADR-0012 records the fix: after NORMALIZED the workflow asks `list_packet_children`, starts
one child workflow per packet, awaits them, and advances the parent to COMPLETED. Children
need no flag — `advance_stage` is idempotent by status index, so a child no-ops through
NORMALIZED without re-normalizing, and its own empty child list terminates the recursion.
The guard is the data, not a boolean that can drift from it.

The test uses a **blank separator page**, not a feature-distance boundary. `HeuristicSplitter`
has two independent signals and the blank-page one is unconditional, so this test does not
depend on CP13's tuned `_BOUNDARY_DISTANCE_THRESHOLD`. It is a fan-out test, not a splitter
test; coupling them would make a CP13 retune surface as a CP15 regression. It asserts each
child audits exactly **8** status changes (9 would mean a child re-normalized), the parent
exactly **2**, and that packet 2's page renumbers to 1 while still pointing at
`page-0003.png` — proving the separator was dropped and the renumbering is right.

### The integration tests that had never run

CP15 could not close until they did, and getting there consumed most of a day on
infrastructure rather than code. Recorded because the failure modes were instructive:

- **MinIO's `InvalidAccessKeyId` was never a credentials problem.** Another local project's
  MinIO held ports 9000/9001, so `cw-minio` had failed to bind and never started, and boto3
  was authenticating against a stranger. A foreign MinIO on that port returns
  `InvalidAccessKeyId` rather than refusing the connection, which is why it read as bad
  credentials for an afternoon. Remapped to 19000/19001 following the precedent the compose
  file already set for Postgres (15432), and `test_wiring_unit` now reads the host port out
  of `docker-compose.yml` so the config default cannot drift from the mapping again.
- **Three Docker images had corrupt local layers** (`exec format error`), a legacy of the
  crash that also killed Postgres and MinIO with exit 255. `docker pull` reports "up to
  date" and does nothing when the digest matches, so `docker rmi` first was required.
- **The CP09 skip guard probed Postgres only**, so a down MinIO failed four tests as though
  the code were broken rather than skipping. `ObjectStorage.check_ready()` probes
  `head_bucket` and lets the error through; `exists()` swallows `ClientError` by design,
  which makes a rejected credential indistinguishable from a missing object.
- **The guards had no connect timeout.** A stopped container swallows the SYN rather than
  refusing it, so an 18-test skip took **13 minutes**. `build_engine` gained
  `connect_timeout`; measured 781.99s → 21.72s.

### The hypothesis the measurement overturned

The fan-out test first failed with the activity **cancelled** inside `detect_skew` — the
signature of `start_to_close_timeout`, not of a logic error. The obvious reading was "three
pages exceed a 30s budget," and it was wrong in its mechanism. `scripts/diag_normalize_timing.py`
printed the page size: **4723×6112**, not 1700×2200.

PIL's PDF encoder defaults to `resolution=72`, so saving a 1700×2200 image produces a PDF
whose page *box* is 1700×2200 **points** — a 23.6 × 30.6 inch page. `load_pages` then renders
that at `_PDF_RENDER_DPI = 200` into 28.9 megapixels: **7.7× the pixels, and 3.03s → 57s per
page.** The fixture was the fault, not the page count. Fixed with `resolution=200.0` plus an
assertion pinning the round-trip scale, because a regression there does not announce itself
— it reappears as an unexplained timeout in a different file.

The lesson is the same one CP14 recorded and CP15 repeated three more times this day:
**verify the claim, not something adjacent to it.** A `Server: MinIO` header proves what
software answers a port, never whose instance it is. A linter passing proves nothing if it
is the wrong version reading the wrong config. And a timing number means nothing until you
read the size of the thing being timed.

### Gates at close

| Gate | Result |
|------|--------|
| Extraction accuracy (clean slice) | **98.5%**, 0% missed |
| Mechanism gates (self-verification, off-schema keys, determinism) | green |
| Unit tests | **213** passed |
| Integration — db + ingestion | **18** passed |
| Integration — pipeline (Temporal) | **5** passed, incl. multi-packet fan-out |
| Coverage | 84.06% (gate 80) |
| ruff / ruff format / mypy --strict | clean |

### Carried forward

- **The 30s stage timeout caps a document at ~10 pages** at 3s/page. Real faxes run 5–30.
  A fixed `start_to_close_timeout` is structurally wrong for a stage whose cost is linear in
  pages; the Temporal answer is a generous timeout plus a short `heartbeat_timeout` with
  `_normalize_document` heartbeating per page.
- **`load_pages` applies `_PDF_RENDER_DPI` to any page box, with no size cap.** Its comment
  claims PDF pages come out "comparable in scale" to the synthetic 1700px pages, which holds
  only for a physically letter-sized box. A real upload with an odd box costs 57s/page.
- **`check_ready()` uses boto3's defaults**, so a MinIO-only outage is slow the way Postgres
  was. It does not bite today only because the Postgres probe runs first.
- **`REFERRAL` still declares `label="Diagnosis (ICD-10)"`** — unchanged, and deliberately.
  No generator, no evidence, and guessing is what caused the original bug.
- **`clinical_justification` remains unmeasured.** CP16 inherits it.

## Execution log

| Date | Event |
|------|-------|
| 2026-08-26 | Phase 0 spike: three reading paths measured before any implementation. VLM arms 0/24 groundable; deterministic anchor 23/24. ADR-0011 written; the approved design overturned by evidence. |
| 2026-08-26 | Extractor built. Eval 90.8%, `urgency` 0% while passing self-verification — four wrong hypotheses before reading the source found schema/generator label drift. `test_label_consistency_unit.py` written; it found two further drifts on its first run. |
| 2026-08-27 | Migration 0003 applied and rolled back cleanly; all 9 CP08 RLS isolation tests re-run green on the new schema. |
| 2026-09-02 | Fan-out DB half proven (14 integration tests). `MultipleResultsFound` intake crash found by writing the test. |
| 2026-09-02 | Local stack fully healthy for the first time: MinIO port collision diagnosed, corrupt images re-pulled, skip guards fixed and bounded. CP10's 4 lifecycle tests run for the first time — all pass. |
| 2026-09-02 | ADR-0012 accepted (parent joins on children). Fan-out implemented; test failed on a fixture PDF page-box bug, diagnosed by measurement, fixed. **5/5 pipeline integration tests pass. CP15 closed.** |
