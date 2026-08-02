# chartwright-storage (CP13)

Shared S3-compatible object storage client (MinIO locally, S3 in production).
Extracted from `services/ingestion` in CP13 so `services/pipeline` can read/write the
same buckets without depending on the ingestion service — see ADR-0009 for why this is a
shared `libs/*` package rather than a cross-service import or a duplicated client.

## API

```python
from chartwright_storage import ObjectStorage

storage = ObjectStorage(
    settings
)  # settings only needs the five s3_* fields (structural, see below)
storage.put_original(tenant_id=..., document_id=..., data=..., extension=".pdf")
storage.put_quarantined(tenant_id=..., document_id=..., data=..., extension=".pdf")
storage.put_normalized_page(tenant_id=..., document_id=..., page_number=1, data=...)
storage.get(key)
storage.exists(key)
```

Construction is structural, not by inheritance: `ObjectStorage.__init__` accepts anything
satisfying the `S3SettingsLike` protocol (`s3_endpoint`, `s3_access_key`, `s3_secret_key`,
`s3_bucket`, `s3_region`). Both `ingestion.config.Settings` and
`pipeline.config.PipelineSettings` already define those five fields with matching
defaults, so either constructs an `ObjectStorage` with no shared config import.

## Key layout

| method | key |
|---|---|
| `put_original` | `tenants/{tenant_id}/documents/{document_id}/original{ext}` |
| `put_quarantined` | `quarantine/{tenant_id}/{document_id}{ext}` |
| `put_normalized_page` | `tenants/{tenant_id}/documents/{document_id}/normalized/page-{page_number:04d}.png` |

The key layout is a stable contract other services reason about (see
`tests/test_object_storage_unit.py`) — changing it is a breaking change for every stored
object, not just a refactor.

## Backward compatibility

`services/ingestion/src/ingestion/storage.py` is now a one-line re-export
(`from chartwright_storage import ObjectStorage`), so every existing
`from ingestion.storage import ObjectStorage` import keeps working unchanged. No
ingestion behavior or test changed as part of this extraction.
