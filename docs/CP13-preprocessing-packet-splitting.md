# CP13 — Preprocessing, Normalization & Packet Splitting

- **Status:** Draft (awaiting owner approval per `docs/working-agreements.md` §1)
- **Depends on:** CP12 (Tier-0 OCR + grounding) ✅
- **Feeds:** CP14 (document classification), CP15 (structured extraction)
- **Owns pipeline stage:** `NORMALIZED` (`STATUS_ORDER[1]`, between `RECEIVED` and `CLASSIFIED`)

## Objective

A raw upload from CP09 ingestion is one opaque file: some number of pages, arbitrary
orientation, arbitrary scan/fax quality, and — critically — possibly **more than one
logical document** stapled or faxed together (e.g. a PA form followed by an insurance
card photo and a lab report). Nothing downstream can safely reason about "the document"
until that's resolved.

CP13 turns the raw upload into one or more **normalized page sequences**, each
representing one logical document ready for classification (CP14) and OCR (Tier-0,
already built in CP12). It does not classify, extract, or interpret content — it only
prepares pixels and establishes document boundaries.

## Scope (this checkpoint only — do not build ahead)

### 1. Page-level image normalization
New library `libs/chartwright-preprocess`. Deterministic, pixel-local + geometric
operations applied per page, mirroring (inverting the spirit of) the degradation
techniques already built in `chartwright-synthdata`:

- **Orientation correction** — detect and correct 0/90/180/270° rotation.
- **Deskew** — fine-angle correction (the inverse of the skew CP12's eval slices apply),
  producing a `skew_angle_deg` metadata field per page so it's auditable, not silent.
- **Contrast/denoise normalization** — bring pages toward a consistent contrast band so
  Tier-0 OCR sees comparable input regardless of source scan quality.
- Every transform must be **coordinate-recoverable**: like `degrade.py`'s
  `_rotate_bbox`, downstream grounding must still be able to map a normalized-page
  location back to something meaningful. (Practically: record the transform parameters,
  don't destroy geometry silently.)

### 2. Packet splitting
Given a multi-page upload, partition pages into ordered page-ranges, each an
independent logical document, output as a list of `Packet(pages=[...], boundary_score=...)`.

Because CP14 (classification) doesn't exist yet, splitting must work from **structural
signals only**, not semantic ones:
- Blank/near-blank separator pages (common in fax transmissions).
- Large layout/whitespace discontinuities between adjacent pages (cheap heuristic:
  compare page-level ink-density and margin profiles).
- Explicit machine-readable separator sheets, if any (defer unless trivial).

Design as a **pluggable protocol** (same pattern as `OcrEngine` in CP12): a
`PacketSplitter` protocol with one heuristic implementation now (`HeuristicSplitter`),
so CP14 or later checkpoints can swap in a classifier-informed splitter without changing
the pipeline shape. **The v1 heuristic is expected to be imperfect** — that's fine and
should be stated plainly in the README and eval output, not hidden.

### 3. Pipeline integration
Give the `NORMALIZED` stage in `services/pipeline/src/pipeline/activities.py` a real
body: pull the stored document from CP09's object storage, run normalization +
splitting, and persist the result. Idempotency contract (ADR-0001) must hold — re-running
an already-`NORMALIZED` document is a no-op.

**Open question requiring a decision before implementation:** does "one uploaded file →
N logical documents" require a schema/DB change (CP08's `chartwright-db` currently
models one `Document` row per upload)? Two options:
  - (a) Add a `packets` child table now (minor CP08-adjacent schema change, scoped
    tightly to this need), or
  - (b) Defer multi-packet persistence — CP13 produces packets as an in-memory/blob
    artifact keyed to the document, and splitting the *pipeline* to fan out one
    upload into N downstream documents happens in a later checkpoint once CP14 needs it.

  **Recommendation: (b).** Keep CP13 additive-only against CP08's schema (per the
  Universal DoD: "no scope leaked from a future checkpoint"). Store the packet
  boundaries as normalized-page metadata; defer the fan-out-into-N-documents workflow
  change until CP14 actually needs to classify+route packets independently. Flag this
  explicitly as a follow-up in CP14's spec.

### Explicitly out of scope (belongs to later checkpoints)
- Field-value normalization (dates, phone numbers, code systems) — CP16.
- Document classification itself — CP14.
- Any use of the CP11 model gateway / VLM — preprocessing is deterministic, no model
  calls (matches ADR-0003's "Tier-0 is deterministic" framing from CP12).

## Deliverables
- `libs/chartwright-preprocess` — `normalize_page()`, `PacketSplitter` protocol +
  `HeuristicSplitter`, typed dataclasses for `NormalizedPage` / `Packet`.
- `services/pipeline`: `NORMALIZED` stage wired to real work; idempotency preserved.
- `scripts/eval_preprocess.py` — seed of a CP26-style gate, mirroring CP12's
  `eval_ocr.py` shape: measures orientation-correction accuracy and packet-boundary
  precision/recall against synthetic multi-document packets (extend
  `chartwright-synthdata` with a packet-composition generator — concatenate N synthetic
  documents with optional blank separators, controllable seed).
- README + this spec updated with measured results (not just targets), same discipline
  as CP12's README table.

## Success criteria / gates
- Orientation correction: ≥ 95% correct on synthetic 0/90/180/270 rotated pages.
- Packet-boundary detection: precision and recall both ≥ 85% on synthetic multi-document
  packets (2–4 sub-documents, with and without blank separators) — measured and reported
  honestly, the same way CP12's fax/bad_fax slices were recalibrated to actually
  discriminate rather than reporting a vacuous 100%.
- Normalization is idempotent and lossless-to-geometry: a page normalized twice produces
  the same output; transform parameters are always recoverable.
- All existing tests (CP03–CP12) remain green; coverage gate (≥ 80%) holds.

## Definition of Done
Universal DoD from `docs/definition-of-done.md` applies in full, plus this is an AI-adjacent
(not AI) checkpoint — no model calls, so the "AI checkpoint" DoD section does not apply;
this is closer to the pattern of CP08/CP09 (deterministic service work).

## Execution log
_(filled in during implementation)_
