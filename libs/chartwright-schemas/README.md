# chartwright-schemas

The shared domain vocabulary of the platform, as strict Pydantic v2 models:

- **Grounding contract** (`grounding.py`) — `Provenance`, `GroundedField`, `GroundedTable`: every extracted value carries page + bounding box + source span + calibrated confidence (ADR-0003). This is the type every AI stage produces and every consumer (validation, review console, FHIR output) reads.
- **Taxonomy** (`taxonomy.py`) — the v1 clinical document types (`DocType`) and their review-routing metadata.
- **Extraction schemas** (`documents/`) — the typed field sets per document type (prior-auth request, referral, EOB, lab report, insurance card), plus a `SCHEMA_REGISTRY` mapping `DocType → schema`.
- **Envelope** (`envelope.py`) — `ExtractionResult`: the versioned, document-level container that moves through the pipeline.

Rules embedded in the types (not just docs): confidence is `[0,1]`; bounding boxes are non-negative with positive size; schema instances are versioned (`schema_version`); unknown/absent fields are represented as absent — never invented.

```python
from chartwright_schemas import DocType, SCHEMA_REGISTRY, GroundedField, Provenance

schema_cls = SCHEMA_REGISTRY[DocType.PRIOR_AUTH_REQUEST]
```

Used by every service; changes require a version bump and (from CP26) an eval-gate run.
