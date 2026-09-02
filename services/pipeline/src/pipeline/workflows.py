"""The document lifecycle workflow (ADR-0001/0004): Temporal owns per-document correctness.

Deterministic by construction: the workflow only sequences activities; all I/O lives in
activities. Retries with backoff per stage; exhausted retries route to the FAILED + DLQ
path via ``mark_failed`` — the document is never silently lost.

The HITL wait primitive (used from CP17/CP20 on) is stubbed as a signal handler now so
the workflow shape is final: later checkpoints set ``needs_review`` and the workflow
durably parks at ``wait_for_review`` until a reviewer signals resolution.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from pipeline.activities import (
        PIPELINE_STAGES,
        ChildrenInput,
        FailInput,
        StageInput,
    )

# The stage after which an upload may fan out into packet children (ADR-0012). CP13
# splits during NORMALIZED, so this is the first moment children can exist.
_FANOUT_AFTER_STAGE = "NORMALIZED"

# Reported as `failed_stage` when the upload itself was fine but a packet was not.
# Which packets failed is not duplicated here -- the child Document rows carry their
# own FAILED status, and that is the authoritative record.
_PACKET_FANOUT = "PACKET_FANOUT"


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
    """RECEIVED -> ... -> COMPLETED, durably.

    A multi-packet upload fans out after NORMALIZED: one child workflow per packet, and
    the upload completes when they all do (ADR-0012). Single-packet uploads -- the common
    case -- take the same straight path through the stage loop they always have.
    """

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

            if stage == _FANOUT_AFTER_STAGE:
                fanned_out = await self._run_packets(input, retry)
                if fanned_out is not None:
                    return fanned_out

        return PipelineResult(document_id=input.document_id, final_status="COMPLETED")

    async def _run_packets(self, input: PipelineInput, retry: RetryPolicy) -> PipelineResult | None:
        """Run one child workflow per packet and join on them (ADR-0012).

        Returns ``None`` when this document has no packet children -- the overwhelmingly
        common single-packet case -- and the caller then continues through the stage loop
        exactly as it did before CP15.

        Children need no special casing. They start at NORMALIZED and ``advance_stage``
        is idempotent by status index, so a child running the full stage loop no-ops
        through NORMALIZED *without* re-running normalization, then carries on to
        CLASSIFIED. It asks for its own children, gets none, and proceeds: the recursion
        terminates on the data rather than on a flag that could drift from it.
        """
        children: list[str] = await workflow.execute_activity(
            "list_packet_children",
            ChildrenInput(document_id=input.document_id, tenant_id=input.tenant_id),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )
        if not children:
            return None

        results: list[PipelineResult] = await asyncio.gather(
            *[
                workflow.execute_child_workflow(
                    DocumentPipelineWorkflow.run,
                    PipelineInput(
                        document_id=child_id,
                        tenant_id=input.tenant_id,
                        max_attempts=input.max_attempts,
                        backoff_seconds=input.backoff_seconds,
                    ),
                    # Deterministic, and the same id the trigger would use for a
                    # standalone document -- so a packet cannot be started twice.
                    id=f"doc-{child_id}",
                )
                for child_id in children
            ]
        )

        # Children catch their own retry exhaustion and RETURN a FAILED result rather
        # than raising, so gather() does not throw here: results must be inspected.
        failed = [r.document_id for r in results if r.final_status != "COMPLETED"]
        if failed:
            await workflow.execute_activity(
                "mark_failed",
                FailInput(
                    document_id=input.document_id,
                    tenant_id=input.tenant_id,
                    # Document ids are not PHI. Named so a replay can target them.
                    reason=f"{len(failed)}/{len(results)} packets failed: {', '.join(failed)}",
                ),
                start_to_close_timeout=timedelta(seconds=30),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            return PipelineResult(
                document_id=input.document_id,
                final_status="FAILED",
                failed_stage=_PACKET_FANOUT,
            )

        # Every packet finished, so the upload has. It skips the intervening stages by
        # design: it is the upload, not a document anything extracts from.
        await workflow.execute_activity(
            "advance_stage",
            StageInput(
                document_id=input.document_id,
                tenant_id=input.tenant_id,
                to_status="COMPLETED",
            ),
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=retry,
        )
        return PipelineResult(document_id=input.document_id, final_status="COMPLETED")
