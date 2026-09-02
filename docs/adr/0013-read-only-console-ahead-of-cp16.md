# ADR-0013: A read-only console comes before CP16

- **Status:** Accepted
- **Date:** 2026-09-02
- **Deciders:** Project owner (decision), assistant (options and analysis)
- **Checkpoint:** CP23-L (re-sequenced)
- **Reversibility:** Two-way door (additive service; CP23 supersedes it)

## Context

Fifteen checkpoints in, nothing is visible. The pipeline reads documents at 98.3%
(classification) and 98.5% (extraction), every field carries a bbox per ADR-0003, and the
only way to look at any of it is to read eval output in a terminal.

The roadmap puts the first pixel a long way off. CP23 (frontend foundation, design system
and auth) depends on CP07 (identity/secrets, not started) and CP21 (external API, not
started). CP24 (review console) depends on CP23 plus CP17 and CP20. So on the current
sequence the earliest visible screen is four to six checkpoints away, and every one of
those is gated on work that has nothing to do with looking at a document.

Meanwhile the data is already sitting in Postgres and MinIO in exactly the shape a console
needs: `ExtractedField` carries `bbox {x,y,w,h}`, `page_number`, `confidence`,
`source_span` and `tier`; `DocumentPage` carries the page dimensions to scale an overlay
against; normalized page images are in object storage.

There is a second, less obvious reason to bring this forward. **Grounding is currently
unfalsifiable by eye.** ADR-0011 recorded the CP15 spike's one miss — `Drew Iyer` read as
`Drew lyer`, correctly located and confidently wrong — and stated that grounding proves
*where* text is, never *what was read*. An eval number cannot show you a box sitting on
the wrong words. A rendered overlay can, in one glance. CP16 (validation) and CP17
(confidence calibration) are both about deciding which extractions to trust, and building
them blind to what the boxes actually look like is the pattern that produced CP14's 28.3%.

The repository already has a precedent for this exact move: **CP04-L** replaced CP04's
sequencing per ADR-0007, substituting a local Docker Compose platform for cloud IaC and
leaving CP04 in the roadmap untouched.

## Options considered

### Option A — CP23-L: a server-rendered read-only console, now
- Pros: smallest thing that puts real grounded data on screen. Reads Postgres through
  `tenant_context` (so RLS still enforces tenancy — no auth is invented or bypassed) and
  MinIO through the existing `ObjectStorage`. No new infrastructure, no API layer, no
  framework decision. Becomes a debugging instrument for CP16/CP17, not just a demo.
  Follows CP04-L's established pattern for a re-sequenced local substitute.
- Cons: it is not CP23. No design system, no auth, no Next.js foundation. A disposable UI
  that proves useful has a way of becoming permanent and unowned.

### Option B — Keep the sequence; wait for CP23/CP24
- Pros: no process deviation; the console arrives with auth, design tokens and an API.
- Cons: four to six checkpoints of building extraction and validation logic with no way to
  see a single bounding box. CP16 and CP17 are precisely the checkpoints that need eyes.

### Option C — Throwaway spike, no checkpoint
- Pros: fastest to a screenshot; no process debt.
- Cons: no DoD, no tests, nothing carries forward, and "temporary" UIs outlive their
  excuse. The honest version of this option is Option A with the scope written down.

## Decision

**Option A.** Build **CP23-L — Read-only review console (local)** before CP16, as a
re-sequenced local substitute in the CP04-L mould. It is a small server-rendered service
that reads the database and object storage directly, lists documents (with packet children
nested under their parent), and renders each page image with its extracted fields drawn as
boxes over the pixels they came from.

**Read-only, and enforced as such.** `ExtractedField` already has `review_action`,
`corrected_value` and `reviewed_by` columns waiting for CP24. CP23-L writes none of them.
Human-in-the-loop review is CP24's scope and depends on CP17's confidence signal; adding
an accept/edit button here would be scope leaked from a future checkpoint, which the
universal DoD forbids.

**Server-rendered, not a SPA.** A JSON API is CP21 and a component framework is CP23;
choosing either here would prejudge a decision this checkpoint has no business making.

## Consequences

- **Positive:** grounding becomes falsifiable by eye. A box drawn over the wrong words is
  obvious in a way no accuracy percentage is, and CP16/CP17 get to be built by people who
  have looked at the failures. It also gives the project something to show — for a
  health-tech founder that is not a vanity concern, it is how the work gets funded.
- **Tenancy is not weakened.** Reads go through `tenant_context`, so Postgres RLS applies
  exactly as it does everywhere else. The dev-tenant header pattern from CP09 carries over
  unchanged; no authentication is invented to fill CP07's gap.
- **Negative / trade-offs:**
  - **This is explicitly not CP23**, and the roadmap keeps CP23 unchanged. No design
    system, no auth, no Next.js, no WCAG audit, no E2E suite. The frontend DoD clauses it
    does *not* satisfy are listed in the checkpoint spec rather than quietly skipped —
    CP14 recorded a skipped integration test satisfying a DoD clause while proving
    nothing, and that must not recur in a new form.
  - **A useful disposable tool tends to become load-bearing.** Mitigated by naming it
    `-L`, keeping CP23 in the roadmap, and stating in the spec that CP23 supersedes it.
    Not eliminated.
  - **It renders whatever the database holds.** Development is synthetic-only per the
    project's standing constraint, and that constraint now has a screen attached to it.
    No PHI in browser storage means no browser storage at all here.
- **Follow-ups:**
  - CP23 supersedes this; CP24 adds the review actions the columns are already waiting for.
  - If the console makes a class of extraction failure obvious, that finding belongs in
    CP16's spec as an acceptance case — the point of building it now.

## Links

- ADR-0007 / CP04-L (the re-sequencing precedent this follows)
- ADR-0003 (grounding contract) · ADR-0011 (grounding proves *where*, never *what*)
- `docs/definition-of-done.md` (frontend DoD) · `docs/design/dashboard-reference.md` (CP25,
  a different screen with a different bar)
