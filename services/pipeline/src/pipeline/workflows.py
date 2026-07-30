"""The document lifecycle workflow (ADR-0001/0004): Temporal owns per-document correctness.

Deterministic by construction: the workflow only sequences activities; all I/O lives in
activities. Retries with backoff per stage; exhausted retries route to the FAILED + DLQ
path via ``mark_failed`` — the document is never silently lost.

The HITL wait primitive (used from CP17/CP20 on) is stubbed as a signal handler now so
the workflow shape is final: later checkpoints set ``needs_review`` and the workflow
durably parks at ``wait_for_review`` until a reviewer signals resolution.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from pipeline.activities import PIPELINE_STAGES, FailInput, StageInput


@dataclass
class PipelineInput:
    document_id: str
    tenant_id: str
    max_attempts: int = 3
    backoff_seconds: float = 0.2


@dataclass
class PipelineResult:
    document_id: str
    final_status: str
    failed_stage: str | None = None


@workflow.defn
class DocumentPipelineWorkflow:
    """RECEIVED -> ... -> COMPLETED, durably. Stage bodies are stubs until CP13+."""

    def __init__(self) -> None:
        self._review_resolved = False

    @workflow.signal
    def resolve_review(self) -> None:
        """HITL resolution signal (consumed from CP20 on; wired now to fix the shape)."""
        self._review_resolved = True

    @workflow.run
    async def run(self, input: PipelineInput) -> PipelineResult:
        retry = RetryPolicy(
            maximum_attempts=input.max_attempts,
            initial_interval=timedelta(seconds=input.backoff_seconds),
            backoff_coefficient=2.0,
        )
        for stage in PIPELINE_STAGES:
            try:
                await workflow.execute_activity(
                    # Activities are registered from a class instance on the worker;
                    # referenced here by name to keep the workflow import-clean.
                    "advance_stage",
                    StageInput(
                        document_id=input.document_id,
                        tenant_id=input.tenant_id,
                        to_status=stage,
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=retry,
                )
            except Exception:
                # Retries exhausted (or non-retryable): terminal-fail + DLQ, never lose it.
                await workflow.execute_activity(
                    "mark_failed",
                    FailInput(
                        document_id=input.document_id,
                        tenant_id=input.tenant_id,
                        reason=f"stage {stage} failed after {input.max_attempts} attempts",
                    ),
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                return PipelineResult(
                    document_id=input.document_id,
                    final_status="FAILED",
                    failed_stage=stage,
                )
        return PipelineResult(document_id=input.document_id, final_status="COMPLETED")
