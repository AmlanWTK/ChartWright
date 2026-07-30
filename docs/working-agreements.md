# Working Agreements

How we build Chartwright. These are the process rules that make the checkpoint model work.

## 1. Checkpoint workflow

1. **Specify** — the checkpoint has a spec (objective, tasks, deliverables, success criteria, DoD).
2. **Approve** — the owner explicitly approves before any code is written.
3. **Implement** — only that checkpoint; never build ahead into future checkpoints.
4. **Test** — unit/integration/E2E + eval + security checks as applicable.
5. **Review** — against the Definition of Done.
6. **Mark complete** — update status; fill the execution log.
7. **Proceed** — only when dependencies are ✅.

**Rules:** never skip a checkpoint · never combine two into one implementation · never generate code for future checkpoints · always justify non-trivial decisions (via ADR) · always propose a better alternative when one exists.

## 2. Branching & version control

- **Remote:** `https://github.com/AmlanWTK/ChartWright.git`. Each checkpoint is pushed to `main` only after it is finished, tested, and approved.
- `main` is always releasable (once CI exists at CP02).
- Feature branches per checkpoint/task: `cpNN/short-description`.
- Conventional commits (`feat:`, `fix:`, `docs:`, `chore:`, `test:`, `refactor:`).
- No direct pushes to `main`; changes land via reviewed PRs (once CP02 sets up CI/branch protection).

## 3. Code review

- Every PR reviewed against the checkpoint's success criteria + DoD.
- Reviewer checks: correctness, tests, security, observability, and that scope didn't leak into a future checkpoint.
- Security-sensitive PRs (auth, PHI paths) get extra scrutiny.

## 4. Definitions & decisions

- Non-trivial architectural decisions get an **ADR** (`docs/adr/`), using the template.
- Requirements changes update the **traceability matrix**.
- Domain terms live in the glossary (below) to keep language consistent.

## 5. Documentation

- Docs live beside code; each service gets a README.
- Diagrams as Mermaid in `docs/architecture/`.
- The roadmap (`docs/ROADMAP.md`) reflects current status.

## 6. Quality bar (per checkpoint DoD — see `definition-of-done.md`)

Tests green · required coverage met · eval targets met (AI) · security checks pass · benchmarks met (where applicable) · deliverables reviewed · execution log updated · owner approves.

## 7. Data & compliance rules (always)

- **No real PHI in development.** Synthetic + de-identified only.
- **No PHI in logs, traces, metrics, commit history, or non-BAA prompts.**
- **No secrets in code or images.**
- Frontier model use only under BAA with minimization.

## 8. Glossary (domain terms)

| Term | Meaning |
|------|---------|
| PA | Prior authorization |
| EOB | Explanation of benefits |
| HITL | Human-in-the-loop |
| VLM | Vision-language model |
| Grounding | Linking each extracted value to its pixel location + source span |
| Cascade / router | Cost-aware selection of model tier per page |
| Tier 0/1/2 | Self-hosted OCR VLM / fine-tuned domain VLM / frontier API |
| Straight-through | Processed without human edits |
| FHIR | Fast Healthcare Interoperability Resources (HL7 R4) |
| CMS-0057-F | The federal rule mandating FHIR PA APIs by Jan 1, 2027 |
| Gold set | Versioned ground-truth data for evaluation |
| ECE | Expected calibration error |

## 9. Cadence

One checkpoint at a time. Each is a natural review + approval point. Milestones (M1–M6) are the demo-able releases.
