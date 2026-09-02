# CP23-L — Read-only review console (local)

- **Status:** 🟡 Specified — awaiting owner approval
- **Re-sequenced ahead of CP16 per ADR-0013.** Substitutes for CP23/CP24's *visibility*
  only. CP23 (frontend foundation, design system, auth) and CP24 (HITL review console)
  remain in the roadmap unchanged and supersede this.
- **Depends on:** CP15 (extraction + fan-out), CP13 (normalized pages), CP08 (RLS)

## Objective

Make the pipeline's output visible, and make grounding falsifiable by eye.

ADR-0011 recorded CP15's one spike miss: `Drew Iyer` read as `Drew lyer` — correctly
located, confidently wrong. Grounding proves *where* text is, never *what was read*. No
accuracy percentage can show a box sitting on the wrong words; a rendered overlay shows it
in one glance. CP16 (validation) and CP17 (calibration) both decide which extractions to
trust, and building them without having looked at the failures is how CP14 reached 28.3%.

## Scope

### 1. `services/console` — a small server-rendered FastAPI app

Reads through the existing libraries; introduces no new dependency on infrastructure.

- `chartwright_db` via `tenant_context` — Postgres RLS applies exactly as elsewhere.
- `chartwright_storage.ObjectStorage.get` — page images streamed from MinIO.
- Tenant selection uses CP09's dev-tenant header/query pattern. **No authentication is
  invented** to fill CP07's gap; the constraint is stated, not worked around.

### 2. Screens

**Document list** — id, source channel, status, doc type, page count, created time.
Packet children nested under their parent, showing packet index, so ADR-0012's fan-out is
visible as a shape rather than inferred from a row count.

**Document detail** — for each page: the normalized page image with every `ExtractedField`
for that page drawn as a box over it, positioned from `bbox {x,y,w,h}` scaled against
`DocumentPage.width/height`. Beside it, the field list: `field_key`, `value_raw`,
`confidence`, `tier`, `source_span`, and a `needs_review` marker.

Hovering or selecting a field highlights its box, and vice versa. That link is the whole
point of the screen — it is what turns "98.5%" into "this box is on the wrong words".

### 3. Explicitly out of scope

- **Any write.** `review_action`, `corrected_value` and `reviewed_by` exist on
  `ExtractedField` and stay untouched. Accept/edit/reject is CP24, gated on CP17's
  confidence signal; adding it here would be scope leaked from a future checkpoint.
- **Authentication, sessions, users.** CP07/CP23.
- **A JSON API.** CP21. Server-rendered HTML only.
- **A component framework or design system.** CP23. The `frontend/` workspace stays the
  CP02 stub it is.
- **Ops metrics, charts, quotas.** CP25, and `docs/design/dashboard-reference.md` sets a
  quality bar for that screen which this one does not attempt.
- **Browser storage of any kind.** No localStorage, no sessionStorage — the frontend DoD
  forbids PHI in browser storage, and the cleanest way to satisfy that is to store nothing.

## Success criteria / gates

| # | Gate |
|---|------|
| 1 | A synthetic multi-packet upload is visible as a parent with its packet children nested beneath it. |
| 2 | Every extracted field renders a box, and each box lands on the pixels its `source_span` came from — verified by inspecting screenshots, not by a passing assertion. |
| 3 | Cross-tenant read returns nothing (the CP08 isolation test extended through the HTTP layer, as CP09 did for intake). |
| 4 | No write path exists to `extracted_fields` from this service — asserted by test, not by convention. |
| 5 | `ruff` / `ruff format` / `mypy --strict` clean; coverage gate holds. |

## Definition of Done — and what it deliberately does not satisfy

Universal DoD applies in full. The **frontend DoD** does not, and the gaps are recorded
here rather than skipped silently:

| Frontend DoD clause | Status |
|---|---|
| No PHI in browser storage; tenant enforced server-side | ✅ Met — no browser storage at all; RLS enforces tenancy in Postgres |
| Accessibility: WCAG 2.1 AA | ⚠️ **Not met.** Semantic HTML and adequate contrast, but no audit. CP23 owns the accessibility bar and its design tokens. |
| E2E tests on critical flows | ⚠️ **Partially met.** An integration test drives the HTTP layer against real Postgres + MinIO; there is no browser-driven E2E suite. CP23 owns that. |

Stating this matters. CP14 recorded a skipped integration test satisfying a DoD clause
while proving nothing, and CP15 watched four tests fail for a missing dependency because a
guard only checked half of it. A partially-met DoD written down is a known debt; a
partially-met DoD left implicit is the next incident.

**Verification step (required):** take screenshots of the document list and a
multi-packet document detail, and inspect the boxes against the page images. The gate is
whether the overlay is *right*, which only an eye can judge.

## Risks

- **A disposable tool becoming load-bearing.** Mitigated by the `-L` name and by CP23
  remaining in the roadmap; not eliminated.
- **The overlay looks right while being subtly wrong** (off-by-one page, y-axis origin
  flipped, coordinates normalized vs absolute). Gate 2 is inspection precisely because an
  assertion that the box exists proves nothing about where it is.
- **Seeing output invites scope creep toward CP24.** The read-only constraint is enforced
  by test (gate 4), not by discipline.

## Execution log
- (empty — awaiting approval)
