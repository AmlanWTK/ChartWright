# Definition of Done (DoD)

The universal quality bar. A checkpoint is **complete** only when **all applicable** items pass. Each checkpoint spec also has its own specific DoD; this is the baseline that always applies.

## Universal DoD (every checkpoint)

- [ ] All tasks in the checkpoint spec are complete.
- [ ] Code reviewed and approved via PR (from CP02 onward).
- [ ] Unit + integration tests pass; required coverage met (≥ 80% on core services; 100% on critical paths).
- [ ] No scope leaked from a future checkpoint.
- [ ] Deliverables produced and reviewed against the checkpoint's success criteria.
- [ ] Documentation updated (README/service docs/diagrams/ADRs as needed).
- [ ] Observability in place for new components (traces/metrics/logs, PHI-safe).
- [ ] Security checks pass (SAST/deps/secret scans; auth where relevant).
- [ ] No secrets in code/images; no PHI in logs.
- [ ] Execution log in the checkpoint spec updated (PRs, decisions, deviations).
- [ ] **Owner explicitly approves.**

## Additional DoD for AI checkpoints

- [ ] Relevant eval metrics meet targets on the versioned gold set.
- [ ] Grounding/provenance present where fields are produced.
- [ ] Confidence calibration within tolerance (where confidence is emitted).
- [ ] Hallucination rate within target.
- [ ] Change passes the CI eval gate (from CP26 onward).

## Additional DoD for infrastructure checkpoints

- [ ] Fully reproducible from IaC (fresh-environment rebuild works).
- [ ] IaC scanned (Checkov) with no high-severity findings.
- [ ] Encryption + network isolation verified.
- [ ] Rollback path documented and tested.

## Additional DoD for frontend checkpoints

- [ ] Accessibility: WCAG 2.1 AA on new screens.
- [ ] E2E tests on critical flows.
- [ ] No PHI in browser storage; tenant enforced server-side.

## Additional DoD for security/compliance checkpoints

- [ ] Threat model updated.
- [ ] Tenant-isolation attempt fails (where applicable).
- [ ] No open critical/high findings.
- [ ] Control-to-requirement mapping updated.

## Verification step (required for non-trivial checkpoints)

Each checkpoint includes an explicit verification action appropriate to its type — e.g., run the eval harness, take/inspect screenshots, run the isolation test, perform a DR drill, or generate and review a diff — before it can be marked done.
