"""Unit tests: CP15's OCR_DONE and EXTRACTED stage wiring — construction and pure logic.

No live Postgres/Temporal/S3/OCR engine: storage, repository and the OCR engine are all
injected fakes, following test_classify_wiring_unit.py's pattern. Full pipeline behavior
is an integration concern (`make local-up && make test-integration`).

The fake storage deliberately borrows ObjectStorage's *real* key function rather than
re-deriving the path. OCR_DONE writes a key and EXTRACTED reads it back; if those two ever
disagree the pipeline silently loses its OCR, and a fake with its own copy of the format
would hide exactly that.
"""

import uuid
from unittest.mock import MagicMock

import pytest
from chartwright_events import LoggingEventPublisher
from chartwright_ocr import OcrToken, PageOcr, page_ocr_to_json
from chartwright_schemas import BoundingBox
from chartwright_storage import ObjectStorage
from pipeline.activities import PipelineActivities
from pipeline.config import PipelineSettings

TENANT = uuid.uuid4()
DOC_ID = uuid.uuid4()


def tok(text: str, x: float, y: float, w: float = 90.0, h: float = 26.0):
    return OcrToken(text=text, bbox=BoundingBox(x=x, y=y, w=w, h=h), confidence=0.95)


def _form_page() -> PageOcr:
    return PageOcr(
        width=1700,
        height=2200,
        tokens=(
            tok("Member", 90, 200),
            tok("ID:", 190, 200),
            tok("A21743360", 600, 200),
        ),
    )


class FakeStorage:
    """Serves page images by key and records what was written."""

    # The real key function, not a copy of it — see module docstring.
    ocr_page_key = staticmethod(ObjectStorage.ocr_page_key)

    def __init__(self, blobs: dict[str, bytes] | None = None) -> None:
        self.blobs: dict[str, bytes] = blobs or {}
        self.written: dict[str, bytes] = {}

    def get(self, key: str) -> bytes:
        return self.blobs[key]

    def put_ocr_page(
        self, *, tenant_id: uuid.UUID, document_id: uuid.UUID, page_number: int, data: bytes
    ) -> str:
        key = self.ocr_page_key(
            tenant_id=tenant_id, document_id=document_id, page_number=page_number
        )
        self.written[key] = data
        self.blobs[key] = data
        return key


class FakeOcrEngine:
    name = "fake"

    def __init__(self, page: PageOcr) -> None:
        self._page = page
        self.calls = 0

    def recognize(self, image_bytes: bytes) -> PageOcr:
        self.calls += 1
        return self._page


class FakePage:
    def __init__(self, image_object_key: str | None) -> None:
        self.image_object_key = image_object_key


class FakeRepo:
    """Stands in for DocumentRepository (page lookup only)."""

    def __init__(self, pages: dict[int, FakePage | None]) -> None:
        self._pages = pages

    def get_page(self, document_id: uuid.UUID, page_number: int) -> FakePage | None:
        return self._pages.get(page_number)


class FakeExtractions:
    """Stands in for ExtractionRepository -- a genuinely separate CP08 repository."""

    def __init__(self) -> None:
        self.extractions: list[tuple[str, float | None]] = []
        self.fields: list[tuple[str, str, int]] = []

    def create_extraction(
        self, *, document_id, doc_type: str, schema_version: str, overall_confidence=None
    ):
        self.extractions.append((doc_type, overall_confidence))
        return MagicMock(id=uuid.uuid4())

    def add_field(self, *, extraction_id, field_key: str, value_raw: str, page_number: int, **kw):
        self.fields.append((field_key, value_raw, page_number))
        return MagicMock()


def _doc(page_count: int = 1, doc_type: str | None = "prior_auth_request"):
    doc = MagicMock()
    doc.id = DOC_ID
    doc.page_count = page_count
    doc.doc_type = doc_type
    doc.doc_type_confidence = 0.9
    return doc


def _acts(storage: FakeStorage, engine: FakeOcrEngine | None = None) -> PipelineActivities:
    return PipelineActivities(
        publisher=LoggingEventPublisher(),
        storage=storage,
        gateway=object(),
        ocr_engine=engine or FakeOcrEngine(_form_page()),
        settings=PipelineSettings(),
    )


class TestConstruction:
    def test_default_ocr_engine_constructs_without_loading_models(self) -> None:
        """RapidOcrEngine is lazy; building the activity object must not touch ONNX."""
        acts = PipelineActivities(publisher=LoggingEventPublisher())
        assert acts._ocr_engine is not None

    def test_injected_engine_is_used_instead_of_the_default(self) -> None:
        engine = FakeOcrEngine(_form_page())
        assert _acts(FakeStorage(), engine)._ocr_engine is engine


class TestOcrStage:
    def test_every_page_is_recognized_and_stored(self) -> None:
        storage = FakeStorage({"norm/p1": b"img1", "norm/p2": b"img2"})
        engine = FakeOcrEngine(_form_page())
        acts = _acts(storage, engine)
        repo = FakeRepo({1: FakePage("norm/p1"), 2: FakePage("norm/p2")})

        acts._ocr_document(repo, TENANT, _doc(page_count=2))

        assert engine.calls == 2
        assert len(storage.written) == 2
        assert all(k.endswith(".json") for k in storage.written)

    def test_missing_normalized_image_is_a_hard_error(self) -> None:
        acts = _acts(FakeStorage())
        repo = FakeRepo({1: FakePage(None)})
        with pytest.raises(RuntimeError, match="no normalized image"):
            acts._ocr_document(repo, TENANT, _doc())

    def test_document_with_no_pages_is_a_hard_error(self) -> None:
        acts = _acts(FakeStorage())
        with pytest.raises(RuntimeError, match="no pages"):
            acts._ocr_document(FakeRepo({}), TENANT, _doc(page_count=0))


class TestExtractStage:
    def test_reads_back_what_the_ocr_stage_wrote_and_records_fields(self) -> None:
        """The end-to-end contract between the two stages, through the real key format."""
        key = ObjectStorage.ocr_page_key(tenant_id=TENANT, document_id=DOC_ID, page_number=1)
        storage = FakeStorage({key: page_ocr_to_json(_form_page())})
        acts = _acts(storage)
        extractions = FakeExtractions()

        acts._extract_document(extractions, TENANT, _doc())

        assert extractions.extractions == [("prior_auth_request", pytest.approx(0.95, abs=0.05))]
        assert ("member_id", "A21743360", 1) in extractions.fields

    def test_unclassified_document_is_a_hard_error(self) -> None:
        acts = _acts(FakeStorage())
        with pytest.raises(RuntimeError, match="without a doc_type"):
            acts._extract_document(FakeExtractions(), TENANT, _doc(doc_type=None))

    def test_fields_the_page_does_not_support_are_absent(self) -> None:
        key = ObjectStorage.ocr_page_key(tenant_id=TENANT, document_id=DOC_ID, page_number=1)
        storage = FakeStorage({key: page_ocr_to_json(_form_page())})
        acts = _acts(storage)
        extractions = FakeExtractions()

        acts._extract_document(extractions, TENANT, _doc())

        keys = {k for k, _, _ in extractions.fields}
        assert "procedure_code" not in keys  # nothing on this page supports it
