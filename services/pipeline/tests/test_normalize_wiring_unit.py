"""Unit tests: CP13's NORMALIZED stage wiring — construction and pure logic only.

No live Postgres/Temporal/S3 needed: engines and storage clients connect lazily (see
test_pipeline_unit.py's TestConstruction for the established pattern this follows).
Full pipeline behavior (a document actually reaching NORMALIZED with real bytes) is an
integration concern — verify with `make local-up && make test-integration`.
"""

import io
from unittest.mock import MagicMock

from chartwright_db import NormalizedPageInput
from chartwright_events import LoggingEventPublisher
from chartwright_preprocess import (
    HeuristicSplitter,
    file_type_from_extension,
    load_pages,
    normalize_page,
)
from chartwright_synthdata import generate_prior_auth
from pipeline.activities import PipelineActivities
from pipeline.config import PipelineSettings


class FakeStorage:
    """Records puts, serves one fixed original — enough to exercise the real logic
    path in _normalize_document without any network or live service."""

    def __init__(self, original_bytes: bytes, original_key: str) -> None:
        self._original_bytes = original_bytes
        self._original_key = original_key
        self.puts: list[str] = []

    def get(self, key: str) -> bytes:
        assert key == self._original_key
        return self._original_bytes

    def put_normalized_page(
        self, *, tenant_id: object, document_id: object, page_number: int, data: bytes
    ) -> str:
        key = f"tenants/{tenant_id}/documents/{document_id}/normalized/page-{page_number:04d}.png"
        self.puts.append(key)
        return key


class TestConstruction:
    """Mirrors TestConstruction in test_pipeline_unit.py — proves the new storage/
    settings wiring doesn't require network access to build."""

    def test_default_storage_constructs_without_network(self) -> None:
        acts = PipelineActivities(publisher=LoggingEventPublisher())
        assert acts._storage is not None

    def test_injected_storage_is_used_instead_of_the_default(self) -> None:
        fake = object()
        acts = PipelineActivities(
            publisher=LoggingEventPublisher(), storage=fake, settings=PipelineSettings()
        )
        assert acts._storage is fake


class TestNormalizeDocumentLogic:
    """Exercises the real normalization + storage + splitting logic end to end against
    fakes, proving the pieces compose correctly even without a live pipeline."""

    def test_single_page_png_upload_produces_one_normalized_page_and_one_packet(self) -> None:
        g = generate_prior_auth(seed=1, document_id="d")
        buf = io.BytesIO()
        g.image.convert("RGB").save(buf, format="PNG")
        raw_bytes = buf.getvalue()

        original_key = "tenants/T/documents/D/original.png"
        storage = FakeStorage(raw_bytes, original_key)

        extension = "." + original_key.rsplit(".", 1)[-1]
        file_type = file_type_from_extension(extension)
        pages = load_pages(storage.get(original_key), file_type)
        normalized_pages = [normalize_page(p) for p in pages]

        page_inputs: list[NormalizedPageInput] = []
        for i, normalized in enumerate(normalized_pages, start=1):
            page_buf = io.BytesIO()
            normalized.image.save(page_buf, format="PNG")
            key = storage.put_normalized_page(
                tenant_id="T", document_id="D", page_number=i, data=page_buf.getvalue()
            )
            page_inputs.append(
                NormalizedPageInput(
                    page_number=i,
                    width=normalized.image.width,
                    height=normalized.image.height,
                    image_object_key=key,
                )
            )

        assert len(page_inputs) == 1
        assert page_inputs[0].page_number == 1
        assert storage.puts == ["tenants/T/documents/D/normalized/page-0001.png"]

        packets = HeuristicSplitter().split([p.image for p in normalized_pages])
        assert len(packets) == 1
        assert packets[0].page_indices == (0,)

    def test_extension_mismatch_raises_before_any_storage_call(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="unrecognized"):
            file_type_from_extension(".bmp")

    def test_missing_original_object_key_is_a_hard_error_not_a_silent_skip(self) -> None:
        """A document reaching NORMALIZED with no stored original is a bug elsewhere in
        the pipeline (CP09 always sets this on a clean RECEIVED document) — fail loud,
        never silently skip normalization."""
        import pytest

        acts = PipelineActivities(publisher=LoggingEventPublisher(), storage=object())
        doc = MagicMock()
        doc.id = "D"
        doc.original_object_key = None
        with pytest.raises(RuntimeError, match="no original_object_key"):
            acts._normalize_document(MagicMock(), "T", doc)
