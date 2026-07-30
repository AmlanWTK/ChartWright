# Security Policy

Chartwright processes Protected Health Information (PHI) and is designed to a HIPAA/SOC 2 posture. Security is treated as architectural — see `docs/threat-model-v0.md` (deepened at CP29).

## Reporting a vulnerability

Please report suspected vulnerabilities privately to the project owner (do **not** open a public issue). Include steps to reproduce and impact. We aim to acknowledge within a few business days.

## Ground rules for contributors

- **Never commit secrets.** Secret scanning (gitleaks) runs locally and in CI.
- **Never commit PHI** — not in code, tests, fixtures, logs, or commit messages. Use synthetic/de-identified data only.
- No PHI in logs, traces, metrics, or prompts sent to non-BAA providers.
- Dependencies are scanned (Trivy, Dependabot); high/critical findings block merges.
- Static analysis (Semgrep, CodeQL) runs on every PR.

## Supported scope

This is pre-release software under active checkpoint-based development. Security controls are progressively hardened; the formal control mapping and penetration test are completed at CP29 before any production launch (CP34).
