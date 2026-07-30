# pipeline service (CP10)

The orchestration backbone (ADR-0001/0004): a **Temporal workflow** durably walks each
document through the state machine (`RECEIVED → NORMALIZED → … → COMPLETED`) with
per-stage retries; **Kafka** decouples ingestion from processing; failures land in
**FAILED + a DLQ event**, never lost; any document can be **replayed**.

Stage bodies are stubs that only advance the (audited) state machine — later checkpoints
(CP13 preprocess, CP14 classify, CP15 extract, …) fill in real work without changing the
workflow shape. The HITL `resolve_review` signal is wired now for the same reason.

## Key design points

- **Idempotent stages:** re-running a transition the document already passed is a no-op
  (status-order check), so retries/replays are safe.
- **Exactly-once starts from at-least-once delivery:** the trigger derives the workflow
  ID from the document ID; Temporal rejects duplicate starts server-side.
- **Poison hook:** `external_ref = "poison:<STAGE>"` fails that stage deterministically —
  the DLQ/chaos path is testable on demand.

## Run locally (stack up + migrations applied)

```powershell
# terminal 1 — the worker (run several to see work sharing)
uv run python -m pipeline.worker

# terminal 2 — the Kafka->Temporal trigger
uv run python -m pipeline.trigger

# terminal 3 — ingestion publishing REAL events now
$env:CHARTWRIGHT_EVENT_PUBLISHER = "kafka"
uv run uvicorn ingestion.main:app --port 8100
```

Upload a document (see ingestion README) and watch it flow: the Temporal UI at
http://localhost:8233 shows the workflow `doc-<document_id>` stepping through every
stage; `GET /v1/documents/{id}` shows the status advancing to `COMPLETED`.

## Replay (DLQ recovery)

```powershell
uv run python scripts/replay_document.py --document-id <uuid> --tenant-id <uuid>
```

## Tests

`pytest -m integration` proves: full lifecycle with a 9-transition audit trail,
poison → FAILED (not lost), duplicate-start rejection, and FAILED → replay → COMPLETED.
The worker runs in-process on a unique task queue, so tests are self-contained.
