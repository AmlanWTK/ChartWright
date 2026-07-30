"""Unit tests: lifecycle-order invariants, poison hook shape, settings defaults."""

from pipeline.activities import PIPELINE_STAGES, STATUS_ORDER, PoisonedDocumentError
from pipeline.config import PipelineSettings
from pipeline.workflows import PipelineInput, PipelineResult


class TestLifecycleInvariants:
    def test_status_order_starts_received_ends_completed(self) -> None:
        assert STATUS_ORDER[0] == "RECEIVED"
        assert STATUS_ORDER[-1] == "COMPLETED"

    def test_pipeline_stages_are_everything_after_received(self) -> None:
        assert STATUS_ORDER[1:] == PIPELINE_STAGES
        assert "RECEIVED" not in PIPELINE_STAGES

    def test_statuses_are_unique(self) -> None:
        assert len(STATUS_ORDER) == len(set(STATUS_ORDER))

    def test_terminal_failure_states_are_not_pipeline_stages(self) -> None:
        for terminal in ("FAILED", "QUARANTINED"):
            assert terminal not in STATUS_ORDER  # they exit the pipeline, not advance it


class TestDataShapes:
    def test_pipeline_input_defaults(self) -> None:
        inp = PipelineInput(document_id="d", tenant_id="t")
        assert inp.max_attempts == 3
        assert inp.backoff_seconds > 0

    def test_pipeline_result_failed_stage_optional(self) -> None:
        ok = PipelineResult(document_id="d", final_status="COMPLETED")
        assert ok.failed_stage is None

    def test_poison_error_is_an_exception(self) -> None:
        assert issubclass(PoisonedDocumentError, Exception)


class TestSettings:
    def test_dev_defaults_match_local_stack(self) -> None:
        s = PipelineSettings()
        assert s.temporal_address.endswith(":7233")
        assert s.kafka_bootstrap.endswith(":9092")
        assert s.task_queue == "chartwright-pipeline"
        assert s.stage_max_attempts >= 1

    def test_settings_factory(self) -> None:
        from pipeline.config import get_pipeline_settings

        assert get_pipeline_settings().task_queue == "chartwright-pipeline"


class TestConstruction:
    """Wiring paths that need no live services (engines/producers connect lazily)."""

    def test_workflow_review_signal_flips_state(self) -> None:
        from pipeline.workflows import DocumentPipelineWorkflow

        wf = DocumentPipelineWorkflow()
        assert wf._review_resolved is False
        wf.resolve_review()
        assert wf._review_resolved is True

    def test_activities_construct_with_injected_publisher(self) -> None:
        from chartwright_events import LoggingEventPublisher
        from pipeline.activities import PipelineActivities

        acts = PipelineActivities(publisher=LoggingEventPublisher())
        assert acts is not None
