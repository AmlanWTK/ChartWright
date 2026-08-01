"""Integration test: real RapidOCR over a synthetic clean page vs. gold labels.

First run downloads/loads the ONNX models (bundled with the wheel; a few seconds).
This is the in-repo slice of the CP12 gate; the full sliced eval is scripts/eval_ocr.py.
"""

import io

import pytest

from chartwright_ocr import RapidOcrEngine, locate_value, verify_at
from chartwright_synthdata import generate_prior_auth

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def recognized():  # type: ignore[no-untyped-def]
    doc = generate_prior_auth(seed=4242, document_id="ocr_itest")
    buf = io.BytesIO()
    doc.image.save(buf, format="PNG")
    try:
        page = RapidOcrEngine().recognize(buf.getvalue())
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"RapidOCR unavailable: {exc}")
    return doc, page


class TestCleanPageRecognition:
    def test_produces_grounded_tokens(self, recognized) -> None:  # type: ignore[no-untyped-def]
        _, page = recognized
        assert len(page.tokens) > 10
        for t in page.tokens:
            assert t.bbox.w > 0 and t.bbox.h > 0
            assert 0.0 <= t.confidence <= 1.0

    def test_field_recall_meets_clean_gate(self, recognized) -> None:  # type: ignore[no-untyped-def]
        """CP12 gate on this page: >= 90% of gold values locatable with grounding."""
        doc, page = recognized
        found = sum(1 for f in doc.labels.fields if locate_value(page, f.value_raw))
        recall = found / len(doc.labels.fields)
        assert recall >= 0.90, f"clean-page field recall {recall:.1%} below 90% gate"

    def test_verifier_confirms_gold_locations(self, recognized) -> None:  # type: ignore[no-untyped-def]
        doc, page = recognized
        confirmed = sum(
            1
            for f in doc.labels.fields
            if verify_at(page, f.value_raw, f.provenance.bbox)
        )
        assert confirmed / len(doc.labels.fields) >= 0.85

    def test_verifier_rejects_fabricated_location(self, recognized) -> None:  # type: ignore[no-untyped-def]
        """Anti-hallucination: a real value claimed at an empty region must fail."""
        from chartwright_schemas import BoundingBox

        doc, page = recognized
        real_value = doc.labels.fields[0].value_raw
        empty_corner = BoundingBox(x=10, y=2100, w=60, h=30)
        assert not verify_at(page, real_value, empty_corner)
