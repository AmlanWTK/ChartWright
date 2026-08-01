"""Unit tests: grounding logic with fabricated tokens — no OCR model needed."""

from chartwright_ocr import (
    OcrToken,
    PageOcr,
    locate_value,
    normalize,
    similarity,
    verify_at,
)
from chartwright_ocr.engine import _reading_order
from chartwright_schemas import BoundingBox


def tok(text: str, x: float, y: float, w: float = 100, h: float = 20) -> OcrToken:
    return OcrToken(text=text, bbox=BoundingBox(x=x, y=y, w=w, h=h), confidence=0.95)


def page(*tokens: OcrToken) -> PageOcr:
    return PageOcr(width=1700, height=2200, tokens=tokens)


class TestNormalization:
    def test_case_and_whitespace_insensitive(self) -> None:
        assert normalize("Member  ID:") == normalize("member id")

    def test_id_meaningful_chars_survive(self) -> None:
        assert "a1234567" in normalize("A1234567")
        assert "03/14/1985" in normalize("03/14/1985")

    def test_similarity_tolerates_ocr_noise(self) -> None:
        assert similarity("A1234567", "Al234567") > 0.75  # 1 -> l confusion


class TestLocateValue:
    def test_exact_single_token(self) -> None:
        p = page(tok("Member", 100, 100), tok("A1234567", 300, 100))
        match = locate_value(p, "A1234567")
        assert match is not None
        assert match.score > 0.99
        assert match.bbox.x == 300

    def test_value_spanning_adjacent_tokens(self) -> None:
        p = page(tok("Alex", 300, 100, w=60), tok("Rivera", 370, 100, w=80))
        match = locate_value(p, "Alex Rivera")
        assert match is not None
        # Envelope covers both tokens:
        assert match.bbox.x == 300
        assert match.bbox.x + match.bbox.w >= 450

    def test_absent_value_returns_none_never_fabricates(self) -> None:
        """THE anti-hallucination property: no evidence -> no location."""
        p = page(tok("Member", 100, 100), tok("A1234567", 300, 100))
        assert locate_value(p, "Z9999999") is None

    def test_noisy_match_found_below_perfect_score(self) -> None:
        p = page(tok("Al234567", 300, 100))  # OCR misread 1 as l
        match = locate_value(p, "A1234567")
        assert match is not None
        assert 0.75 <= match.score < 1.0

    def test_empty_inputs(self) -> None:
        assert locate_value(page(), "anything") is None
        assert locate_value(page(tok("x", 0, 0)), "   ") is None


class TestVerifyAt:
    def test_confirms_value_at_true_location(self) -> None:
        p = page(tok("A1234567", 300, 100))
        assert verify_at(p, "A1234567", BoundingBox(x=290, y=95, w=130, h=30))

    def test_rejects_value_at_wrong_location(self) -> None:
        """A fabricated location claim is caught even when the value exists elsewhere."""
        p = page(tok("A1234567", 300, 100), tok("Standard", 300, 500))
        assert not verify_at(p, "A1234567", BoundingBox(x=300, y=500, w=100, h=20))

    def test_rejects_empty_region(self) -> None:
        p = page(tok("A1234567", 300, 100))
        assert not verify_at(p, "A1234567", BoundingBox(x=1000, y=1000, w=50, h=20))


class TestReadingOrder:
    def test_lines_top_to_bottom_then_left_to_right(self) -> None:
        scrambled = [
            tok("world", 200, 100),
            tok("second", 100, 200),
            tok("hello", 100, 100),
        ]
        ordered = _reading_order(scrambled)
        assert [t.text for t in ordered] == ["hello", "world", "second"]

    def test_slightly_offset_tokens_share_a_line(self) -> None:
        ordered = _reading_order([tok("b", 200, 104), tok("a", 100, 100)])
        assert [t.text for t in ordered] == ["a", "b"]
