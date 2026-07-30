# Document Taxonomy (v1)

The clinical document types Chartwright classifies and (for structured types) extracts. Defined in code at `libs/chartwright-schemas/src/chartwright_schemas/taxonomy.py`; this doc explains the intent.

## Types

| DocType | Description | Structured schema? | Notes |
|---------|-------------|:-----------------:|-------|
| `prior_auth_request` | PA request forms & cover sheets | ✅ | The v1 core workflow |
| `referral` | Specialist referral forms/letters | ✅ | Adjacent workflow, same fields family |
| `eob` | Explanation of benefits | ✅ | Table-heavy (claim lines) |
| `lab_report` | Laboratory results | ✅ | Table-heavy (results panel) |
| `discharge_summary` | Hospital discharge summaries | — | Full-text OCR only in v1 |
| `clinical_note` | Progress/office notes | — | Full-text OCR; evidence source for policy checks |
| `insurance_card` | Member ID cards (front/back) | ✅ | Often phone photos |
| `id_document` | Driver's license, etc. | — | **Always routes to review** (identity risk) |
| `other` | Anything unrecognized | — | **Always routes to review** |

## Design decisions

- **Small and stable on purpose.** Nine types cover the PA workflow end-to-end. Long-tail types belong in `other` + human review rather than in a sprawling, poorly-trained taxonomy. Per-tenant custom types are configuration (post-v1), not code.
- **Structured vs. unstructured split.** Only five types carry field schemas in v1 (`STRUCTURED_TYPES`). Notes and discharge summaries are consumed as *evidence text* by policy reasoning (CP19), which doesn't need per-field grounding to cite passages.
- **Safety rails in the taxonomy itself.** `ALWAYS_REVIEW_TYPES` (`other`, `id_document`) bypass confidence thresholds entirely — misrouting an ID or an unknown document is never a straight-through event.

## Field schemas

Each structured type declares its fields in `documents.py` with three properties that drive the whole pipeline: `kind` (which validator/normalizer applies — CP16), `required` (extraction completeness), and `critical` (the fields bound to the 95%-accuracy NFR: member ID, codes, dates, NPIs — the ones whose errors cause denials).

Tables (`TableSpec`) declare expected column headers so table extraction (CP15) can be structurally validated, not just cell-by-cell.

## Evolution policy

Adding a field/type = minor schema version bump. Changing/removing = major bump + eval-gate run + migration note. `ExtractionResult.schema_version` carries the version through the pipeline so consumers can handle mixed versions during rollout.
