# ADR-0009: Extract `chartwright-storage` as a shared library

- **Status:** Accepted
- **Date:** 2026-08-02
- **Deciders:** Project owner (architecture choice), assistant (implementation)
- **Checkpoint:** CP13
- **Reversibility:** Two-way door (thin re-export keeps the old import path working)

## Context

CP13's NORMALIZED stage needs to read a document's original bytes and write normalized
page images to object storage from `services/pipeline`. The only existing `ObjectStorage`
class lives in `services/ingestion/src/ingestion/storage.py`, built for ingestion's own
`put_original`/`put_quarantined`/`exists`/`get` needs. Two ways to give pipeline the same
capability: (1) have `services/pipeline` depend directly on `services/ingestion` and import
its storage module, or (2) extract the storage client into its own workspace library that
both services depend on.

## Options considered

### Option A — pipeline imports from ingestion directly
- Pros: no new package, smallest diff.
- Cons: creates a service-to-service dependency that doesn't otherwise exist anywhere in
  the codebase (services only share code via `libs/*`, per the existing `chartwright_db`/
  `chartwright_events`/`chartwright_schemas` pattern); couples pipeline's deploy/test
  surface to ingestion's; violates the workspace's own structural convention.

### Option B — extract a shared `libs/chartwright-storage` (chosen)
- Pros: matches the established `libs/*` pattern every other cross-service capability
  already follows; ingestion keeps a zero-behavior-change re-export
  (`from chartwright_storage import ObjectStorage`) so none of its existing imports or
  tests need to change; pipeline depends on the same `libs/*` surface as everything else.
- Cons: one more workspace package to version and lint; the new
  `put_normalized_page()` method needed for CP13 has to live somewhere — this makes that
  somewhere the shared lib rather than either service.

### Option C — duplicate a minimal storage client inside pipeline
- Pros: no shared dependency at all.
- Cons: two independently-drifting implementations of the same S3 key layout and client
  construction logic; the exact kind of duplication `libs/*` exists to avoid.

## Decision

Extract `libs/chartwright-storage/src/chartwright_storage/object_storage.py`: the
`ObjectStorage` class, unchanged (`put_original`, `put_quarantined`, `exists`, `get`), plus
a new `put_normalized_page(*, tenant_id, document_id, page_number, data) -> str` method
for CP13's normalized-page keys
(`tenants/{tenant_id}/documents/{document_id}/normalized/page-{page_number:04d}.png`).
Construction stays structural via an `S3SettingsLike` `Protocol` (five `s3_*` fields), so
both `ingestion.config.Settings` and `pipeline.config.PipelineSettings` satisfy it without
either service importing the other's config. `services/ingestion/src/ingestion/storage.py`
becomes a one-line re-export so every existing `from ingestion.storage import ObjectStorage`
import keeps working unchanged.

## Consequences

- **Positive:** pipeline gets object-storage access through the same `libs/*` seam as
  `chartwright_db`/`chartwright_events`; ingestion's public import path and tests are
  unaffected; the S3 key-layout contract lives in one place instead of two.
- **Negative / trade-offs:** one more workspace member to keep in `mypy_path` and CI; the
  re-export in `ingestion/storage.py` is a small amount of indirection future readers need
  to trace through once.
- **Follow-ups / things to revisit:** if ingestion ever needs storage behavior pipeline
  doesn't (or vice versa), reconsider whether a single shared class is still the right
  shape, or whether it should split into a common base plus per-service extensions.

## Links

- ADR-0001 (async event-driven pipeline, STATUS_ORDER) · `libs/chartwright-storage/` ·
  `docs/CP13-preprocessing-packet-splitting.md`
