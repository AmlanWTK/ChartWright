"""Worker entrypoint: hosts the workflow + activities on the pipeline task queue.

Run:  uv run python -m pipeline.worker
Scaling model (ADR-0001): workers are stateless; run N of them and Temporal distributes
work. Kill one mid-flow and another resumes the workflow exactly where it stopped —
that resilience is CP10's acceptance test.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from pipeline.activities import PipelineActivities
from pipeline.config import get_pipeline_settings
from pipeline.workflows import DocumentPipelineWorkflow
from temporalio.client import Client
from temporalio.worker import Worker

logger = logging.getLogger("chartwright.pipeline.worker")


async def run_worker() -> None:
    settings = get_pipeline_settings()
    client = await Client.connect(settings.temporal_address, namespace=settings.temporal_namespace)
    activities = PipelineActivities()
    worker = Worker(
        client,
        task_queue=settings.task_queue,
        workflows=[DocumentPipelineWorkflow],
        activities=[activities.advance_stage, activities.mark_failed],
        # Our activities are sync (SQLAlchemy is sync); Temporal runs them here.
        activity_executor=ThreadPoolExecutor(max_workers=8),
    )
    logger.info("pipeline worker started (queue=%s)", settings.task_queue)
    await worker.run()


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
