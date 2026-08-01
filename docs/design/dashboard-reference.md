# Design Reference — Ops Dashboard (for CP25)

**Quality bar set by the project owner (2026-07-30):** the Neon console dashboard.
When CP25 (Admin/Ops Dashboards & Developer Portal) is built, it must match this
reference's quality, not a generic admin template.

## What makes the reference excellent (observed traits)

1. **Calm dark theme** — near-black background, low-contrast panel borders, restrained
   accent colors (single blue/purple accent family), generous whitespace.
2. **Hierarchy via scoping, not clutter** — left sidebar scopes context top-down
   (org → project → branch), with section groups (PROJECT / BRANCH / APP BACKEND).
3. **Usage cards with quota fractions** — "0.27 / 100 CU-hrs", "0.03 / 0.5 GB": current
   value + limit in one glance, with info tooltips and a fine-print freshness note
   ("metrics may be delayed by an hour").
4. **Global status pill** — a single "● All OK" health indicator in the header.
5. **Quick-action onboarding cards** — dismissible "get connected" row with 3–4 concrete
   next actions (connection string, CLI init, IDE extension, MCP).
6. **Inline monitoring** — a compact live graph with branch/compute selectors and a
   refresh control, not a separate "metrics" silo.
7. **Resource tables with state chips** — branches listed with compute size, state
   ("Idle"), creator avatar; counts as fractions ("1 / 10 Branch").
8. **Typography discipline** — one type family, few sizes, weight for hierarchy;
   numbers are large, labels small and muted.

## Mapping to Chartwright's CP25 dashboard

| Reference element | Chartwright equivalent |
|-------------------|------------------------|
| Org → project → branch scoping | Org → tenant → environment scoping in sidebar |
| CU-hrs / storage quota cards | Documents today / straight-through % / cost-per-page vs. ceiling / GPU-hrs (tier mix) |
| "All OK" status pill | Pipeline health: worker fleet, Kafka lag, Temporal, DB, storage |
| Monitoring graph + selectors | Throughput & p95 turnaround graph, per-tenant/stage selectors |
| Branch table with state chips | Document queue table: status chips (RECEIVED/…/NEEDS_REVIEW/FAILED), SLA due |
| Quick-action cards | "Connect": API key, upload sample, webhook setup, review console link |
| "1 / 10 Branch" fractions | "N / quota documents this month", "M open review tasks" |

## Implementation notes (when CP25 arrives)

- Stack per `14-frontend-architecture.md`: Next.js + Tailwind + shadcn/ui + Recharts/visx.
- Dark theme as default; design tokens first (spacing/color/type scale) before pages.
- Every metric card binds to a real backend endpoint — no decorative numbers.
- Accessibility bar unchanged: WCAG 2.1 AA (contrast checked against the dark palette).
