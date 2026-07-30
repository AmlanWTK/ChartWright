# ingestion service (CP09)

The front door of the pipeline: accepts document uploads, validates by **magic bytes**
(never trusting client-declared types), **scans** for malware, **dedupes** by sha256
content hash per tenant, stores originals in S3-compatible object storage (MinIO locally),
records everything through the audited CP08 repositories, and emits the `document.received`
event contract that CP10's workflow will consume.

## Run locally (stack up + migrations applied)

```bash
uv run uvicorn ingestion.main:app --reload --port 8100
# docs: http://localhost:8100/docs
```

## Try it

```powershell
# generate a synthetic PA form, then submit it (demo tenant from db-seed)
uv run synthdata --count 1 --out data/try --seed 1
curl.exe -X POST http://localhost:8100/v1/documents `
  -H "X-Tenant-Id: 00000000-0000-0000-0000-00000000000a" `
  -F "file=@data/try/pa_000001.png"
```

Resubmit the same file → same `document_id`, `"dedupe": true`. Check MinIO console
(http://localhost:9001) → bucket `chartwright-documents` → `tenants/<tenant>/documents/...`.

## Pipeline order (and why)

validate → scan → hash → dedupe-or-create → store → audit → emit. Unvetted bytes are never
written to the accepted prefix; infected files are stored under `quarantine/` with a
`QUARANTINED` document row (auditable trail, never processed, no RECEIVED event).

## Deliberate dev/prod seams (all recorded)

| Concern | Local (now) | Production (later checkpoint) |
|---------|-------------|-------------------------------|
| Tenant identity | `X-Tenant-Id` header (**dev-only**) | OIDC + server-side resolution (deferred CP07) |
| Malware engine | EICAR-signature scanner | ClamAV/cloud engine behind the same `Scanner` protocol |
| Event transport | Structured-log publisher | Kafka publisher (CP10), same payload contract |
| Object store | MinIO | S3 + KMS — config change only |

## Tests

- Unit: validation magic-bytes/size, scanner verdicts, event contract.
- Integration (`pytest -m integration`): upload→MinIO object + DB row + audit, dedupe
  round-trip, EICAR→quarantine path, cross-tenant status lookup denied.
