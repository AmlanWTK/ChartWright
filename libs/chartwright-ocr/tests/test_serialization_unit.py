"""Unit tests: PageOcr survives the round trip through object storage (CP15)."""

import pytest
from chartwright_ocr import OcrToken, PageOcr, page_ocr_from_json, page_ocr_to_json
from chartwright_schemas import BoundingBox


def _page() -> PageOcr:
    return PageOcr(
        width=1700,
        height=2200,
        tokens=(
            OcrToken(text="Member", bbox=BoundingBox(x=90, y=200, w=90, h=26), confidence=0.98),
            OcrToken(text="A21743360", bbox=BoundingBox(x=600, y=200, w=180, h=26), confidence=0.9),
        ),
    )


class TestRoundTrip:
    def test_tokens_survive_intact(self) -> None:
        restored = page_ocr_from_json(page_ocr_to_json(_page()))
        assert restored == _page()

    def test_page_geometry_survives(self) -> None:
        restored = page_ocr_from_json(page_ocr_to_json(_page()))
        assert (restored.width, restored.height) == (1700, 2200)

    def test_bboxes_survive_exactly(self) -> None:
        """Grounding is only worth anything if coordinates are bit-stable across stages."""
        restored = page_ocr_from_json(page_ocr_to_json(_page()))
        assert restored.tokens[1].bbox.as_tuple() == (600.0, 200.0, 180.0, 26.0)

    def test_empty_page_round_trips(self) -> None:
        empty = PageOcr(width=100, height=100, tokens=())
        assert page_ocr_from_json(page_ocr_to_json(empty)) == empty

    def test_output_is_utf8_json_bytes(self) -> None:
        blob = page_ocr_to_json(_page())
        assert isinstance(blob, bytes)
        assert blob.startswith(b"{")


class TestMalformedInput:
    """A corrupt OCR blob is an infrastructure fault; fail loudly rather than half-load."""

    @pytest.mark.parametrize("payload", [b"", b"not json", b"[1,2,3]", b'{"width":1}'])
    def test_malformed_payload_raises(self, payload: bytes) -> None:
        with pytest.raises((ValueError, KeyError)):
            page_ocr_from_json(payload)
