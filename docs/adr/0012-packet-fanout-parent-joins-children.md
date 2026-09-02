# ADR-0012: A fanned-out upload completes when its packets complete

- **Status:** Accepted
- **Date:** 2026-09-02
- **Deciders:** Project owner (decision), assistant (options and analysis)
- **Checkpoint:** CP15
- **Reversibility:** Two-way door (workflow shape; no schema change)

## Context

CP13 splits a multi-document upload into packets. CP15 gave that a persistence model
(migration 0003): one child `Document` per packet, each reusing the parent's
`content_hash` and `original_object_key`, each owning page rows renumbered from 1, so
every packet looks like an ordinary single-packet document to CLASSIFIED and beyond.

The workflow was never taught about any of it. `DocumentPipelineWorkflow.run` is a flat
loop over `PIPELINE_STAGES`, so today a multi-packet fax behaves as follows:

- the **parent** — which `_fan_out_packets` documents as *"the upload, not a document to
  extract from"* — is classified, OCR'd, extracted and driven to `COMPLETED` as though it
  were a single document;
- the **children** sit at `NORMALIZED` forever, because nothing starts them.

Both halves are wrong, and the docstring describes behavior that does not exist. All 18
integration tests pass, because the gap is in the workflow layer and none of them run a
workflow. This is the same failure mode as CP15's `urgency` bug: two places that must
agree, with nothing asserting that they do.

## Options considered

### Option A — Parent spawns child workflows, awaits them, then COMPLETED
- Pros: Temporal's child-workflow join is exactly this primitive, so the "all packets
  finished" signal is free rather than built later. CP20 (packet assembly) and CP22 (FHIR
  delivery) both need that signal. No new status, no migration. Failure of any packet is
  observable at one place.
- Cons: the parent's status jumps `NORMALIZED` → `COMPLETED`, skipping six states, so
  `COMPLETED` on a parent means "all my packets completed" rather than "I was extracted".
  Anything reading `status` alone must consult `parent_document_id` to know which it got.

### Option B — Add a terminal `FANNED_OUT` status
- Pros: most honest status semantics; nothing lies about what happened to the parent.
- Cons: `STATUS_ORDER` is a monotonic sequence compared by index (`advance_stage` uses
  `current_idx >= target_idx` for idempotency); a state that *branches* rather than
  sequences does not belong in it without reworking that comparison. And CP20/CP22 still
  need a join, so this defers the real work rather than doing it.

### Option C — Parent stops silently at `NORMALIZED`
- Pros: smallest diff.
- Cons: `NORMALIZED` would mean two different things — "awaiting classification" and
  "finished, fanned out" — distinguishable only by a child lookup. Overloading one value
  with two meanings is precisely what made `Urgency (Standard/Urgent)` fabricate a phone
  number for 100% of documents.

## Decision

**Option A.** After the `NORMALIZED` stage, the workflow asks an activity whether the
document has packet children. If it does, it starts one `DocumentPipelineWorkflow` per
child (workflow id `doc-{child_document_id}`, deterministic because the ids come from an
activity result and are therefore in workflow history), awaits all of them, and then
advances the parent to `COMPLETED`. If it does not, the loop proceeds exactly as today —
single-packet documents are entirely unaffected.

Children need no special casing. They begin at `NORMALIZED`, and `advance_stage` is
already idempotent by index, so a child running the full `PIPELINE_STAGES` loop no-ops
through `NORMALIZED` — importantly *without* re-running `_normalize_document` — and
carries on to `CLASSIFIED`. Recursion terminates because a child's own child list is
always empty; the guard is the query itself, not a flag that could drift out of sync
with reality.

**A failed packet fails the upload.** Child workflows catch their own exhaustion and
return `final_status="FAILED"` rather than raising, so the parent must inspect results
instead of relying on `gather` to throw. If any packet failed, the parent takes the
`mark_failed` path with a reason naming the failed packet indices — it does not report
`COMPLETED`. Per ADR-0001 nothing is silently lost, and an upload whose output is missing
a packet has not succeeded, even partially.

## Consequences

- **Positive:** the fan-out finally does something. Packets are classified and extracted
  independently, which is the entire point of splitting them — a fax containing a PA
  request and an insurance card gets two document types and two schemas instead of one
  wrong one. Retries, backoff and the DLQ path are inherited per packet, so one bad page
  no longer condemns the other packets in the same upload.
- **Negative / trade-offs:**
  - `COMPLETED` is now overloaded on parents, which is Option C's criticism applied to a
    different state. It is narrower — a parent is identifiable by `parent_document_id IS
    NULL` combined with a non-empty child list — but it is real, and any consumer that
    reads status without that context will misread it. **CP21's API and CP24's review
    console must both handle it explicitly rather than inferring.**
  - Partial success is not represented. Three good packets out of four still reports
    `FAILED`. That is the safe reading for now, but it discards information a reviewer
    would want, and CP24 will need the per-child statuses to show what actually happened.
  - Parent-workflow restart after children have run relies on Temporal's default
    id-reuse policy for completed workflows. Worth an explicit policy if restart ever
    becomes routine.
- **Follow-ups:**
  - CP20 assembles the packet from child outputs; this is the join it assembles at.
  - CP24 surfaces per-packet status so a partially failed upload is diagnosable.
  - The lifecycle integration test must cover a multi-packet document end to end. Without
    it this ADR is another docstring describing behavior nothing asserts.

## Links

- ADR-0001 (async pipeline, never silently lose a document) · ADR-0004 (Temporal)
- `docs/CP13-preprocessing-packet-splitting.md` (where packets come from)
- `docs/CP15-structured-extraction.md` · migration `0003_packet_fanout.py`
- `services/pipeline/src/pipeline/workflows.py` · `activities.py::_fan_out_packets`
