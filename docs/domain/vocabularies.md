# Clinical Vocabularies & Code Systems

The canonical code systems Chartwright validates and normalizes against (CP16), with sourcing and update strategy.

## Code systems in v1

| System | Used for | Format rule | Source | Update cadence |
|--------|----------|-------------|--------|----------------|
| **ICD-10-CM** | Diagnoses | Letter + 2 digits, optional dot + up to 4 more (e.g. `M54.16`) | CMS/CDC public release files | Annual (Oct) + errata |
| **CPT** | Procedures | 5 digits (e.g. `72148`); HCPCS Level II alphanumeric later | Licensed from AMA — **licensing required for production**; dev uses format-validation + a small synthetic subset | Annual |
| **NPI** | Providers | 10 digits, Luhn checksum over `80840` + payload | Free NPPES registry (downloadable + API) | Monthly files |
| **Dates** | DOB, DOS | Normalized to ISO 8601 | — | — |
| **Phone** | Contacts | Normalized to E.164 (US default) | — | — |
| **Member IDs** | Coverage | Payer-specific patterns; format sanity only (no registry exists) | Per-payer config | As configured |

## Two-tier validation strategy

1. **Format/checksum validation (always, offline):** shape rules + NPI checksum + date plausibility. Catches transposition and OCR-substitution errors deterministically, with zero external dependencies. This is what CP16 ships first.
2. **Registry validation (where a registry exists):** NPI existence lookups against NPPES; ICD-10 code existence against the release file. Shipped as versioned datasets with a scheduled update job.

## Licensing note (important, recorded early)

CPT is AMA-licensed. Development and evaluation use **format validation plus a small synthetic CPT subset** (the codes in the synthetic-data pools); a production deployment must obtain a CPT license. This is a known commercial prerequisite, not a technical blocker, and is logged in the risk register.

## Versioning

Code-system datasets are versioned artifacts (`icd10cm-2026`, `nppes-2026-07`, …). Validation results record which dataset version was used, so a code that becomes valid/invalid across annual updates is explainable in the audit trail — retired codes must not silently invalidate historical documents.
