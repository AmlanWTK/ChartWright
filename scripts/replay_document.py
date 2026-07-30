"""Replay a document through the pipeline (ops tool for the DLQ path).

Starts a fresh workflow run for a document — typically one that landed in FAILED after
exhausted retries (fix the cause, then replay). Idempotent stages make replay safe:
completed transitions no-op and processing resumes from wherever the document stopped.

Usage:
    uv run python scripts/replay_document.py --document-id <uuid> --tenant-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime

from pipeline.config import get_pipeline_settings
from pipeline.workflows import DocumentPipelineWorkflow, PipelineInput
from temporalio.client import Client


async def replay(document_id: str, tenant_id: str) -> str:
    settings = get_pipeline_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    # Distinct workflow ID per replay: preserves the original run's history for audit
    # while the ID prefix keeps all runs for a document discoverable in the Temporal UI.
    stamp = datetime.now(tz=UTC).strftime("%Y%m%d%H%M%S")
    workflow_id = f"doc-{document_id}-replay-{stamp}"
    handle = await client.start_workflow(
        DocumentPipelineWorkflow.run,
        PipelineInput(document_id=document_id, tenant_id=tenant_id),
        id=workflow_id,
        task_queue=settings.task_queue,
    )
    result = await handle.result()
    return f"{workflow_id}: final_status={result.final_status}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a document through the pipeline.")
    parser.add_argument("--document-id", required=True)
    parser.add_argument("--tenant-id", required=True)
    args = parser.parse_args()
    print(asyncio.run(replay(args.document_id, args.tenant_id)))


if __name__ == "__main__":
    main()
