"""Unit tests: CP14's CLASSIFIED stage wiring — construction and pure logic only.

No live Postgres/Temporal/S3/Ollama needed: engines, storage, and the gateway all
connect lazily (see test_pipeline_unit.py's TestConstruction and
test_normalize_wiring_unit.py, the pattern this follows). Full pipeline behavior is an
integration concern — verify with `make local-up && make test-integration`.
"""

import io
from unittest.mock import MagicMock

from chartwright_events import LoggingEventPublisher
from chartwright_gateway import ModelGateway
from chartwright_gateway.providers import MockProvider
from chartwright_schemas.taxonomy import DocType
from chartwright_synthdata import generate_prior_auth
from pipeline.activities import PipelineActivities
from pipeline.config import PipelineSettings

# A real moondream description, captured during CP14 verification. CP14 classifies by
# describe-then-map (ADR-0010), so the scripted gateway response here is a page
# DESCRIPTION, not the JSON the first implementation used.
_REAL_PA_DESCRIPTION = (
    "The image shows a page of text that appears to be a request for prior "
    "authorization, likely related to a medical or healthcare context."
)


class FakeStorage:
    """Serves one fixed page image — enough to exercise the real logic path in
    _classify_document without any network or live service."""

    def __init__(self, page_bytes: bytes, page_key: str) -> None:
        self._page_bytes = page_bytes
        self._page_key = page_key

    def get(self, key: str) -> bytes:
        assert key == self._page_key
        return self._page_bytes


class FakePage:
    def __init__(self, image_object_key: str | None) -> None:
        self.image_object_key = image_object_key


class FakeRepo:
    """Records classify calls; serves one fixed first page."""

    def __init__(self, page: FakePage | None) -> None:
        self._page = page
        self.classifications: list[tuple[str, float]] = []

    def get_page(self, document_id: object, page_number: int) -> FakePage | None:
        assert page_number == 1
        return self._page

    def record_classification(
        self, document_id: object, *, doc_type: str, confidence: float
    ) -> None:
        self.classifications.append((doc_type, confidence))


def _gateway(scripted_response: str) -> ModelGateway:
    return ModelGateway(tier_chains={0: [MockProvider(response=scripted_response)]})


class TestConstruction:
    """Mirrors TestConstruction in test_pipeline_unit.py / test_normalize_wiring_unit.py
    — proves the new gateway wiring doesn't require network access to build."""

    def test_default_gateway_constructs_without_network(self) -> None:
        acts = PipelineActivities(publisher=LoggingEventPublisher())
        assert acts._gateway is not None

    def test_injected_gateway_is_used_instead_of_the_default(self) -> None:
        fake = object()
        acts = PipelineActivities(
            publisher=LoggingEventPublisher(), gateway=fake, settings=PipelineSettings()
        )
        assert acts._gateway is fake


class TestClassifyDocumentLogic:
    def test_recognizable_description_records_matching_classification(self) -> None:
        g = generate_prior_auth(seed=1, document_id="d")
        buf = io.BytesIO()
        g.image.convert("RGB").save(buf, format="PNG")
        page_key = "tenants/T/documents/D/normalized/page-0001.png"

        acts = PipelineActivities(
            publisher=LoggingEventPublisher(),
            storage=FakeStorage(buf.getvalue(), page_key),
            gateway=_gateway(_REAL_PA_DESCRIPTION),
            settings=PipelineSettings(),
        )
        repo = FakeRepo(FakePage(page_key))
        doc = MagicMock()
        doc.id = "D"

        acts._classify_document(repo, "T", doc)

        assert repo.classifications == [(DocType.PRIOR_AUTH_REQUEST.value, 1.0)]

    def test_unrecognizable_description_records_other_with_zero_confidence(self) -> None:
        g = generate_prior_auth(seed=1, document_id="d")
        buf = io.BytesIO()
        g.image.convert("RGB").save(buf, format="PNG")
        page_key = "tenants/T/documents/D/normalized/page-0001.png"

        acts = PipelineActivities(
            publisher=LoggingEventPublisher(),
            storage=FakeStorage(buf.getvalue(), page_key),
            gateway=_gateway("I have no idea what this is."),
            settings=PipelineSettings(),
        )
        repo = FakeRepo(FakePage(page_key))
        doc = MagicMock()
        doc.id = "D"

        acts._classify_document(repo, "T", doc)

        assert repo.classifications == [(DocType.OTHER.value, 0.0)]

    def test_missing_first_page_is_a_hard_error_not_a_silent_skip(self) -> None:
        """A document reaching CLASSIFIED with no normalized first page is a bug
        elsewhere in the pipeline (NORMALIZED always produces at least one page for a
        clean document) — fail loud, never silently skip classification."""
        import pytest

        acts = PipelineActivities(
            publisher=LoggingEventPublisher(),
            storage=object(),
            gateway=object(),
            settings=PipelineSettings(),
        )
        repo = FakeRepo(None)
        doc = MagicMock()
        doc.id = "D"

        with pytest.raises(RuntimeError, match="no normalized first page"):
            acts._classify_document(repo, "T", doc)
