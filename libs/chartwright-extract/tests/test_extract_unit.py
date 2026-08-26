"""Unit tests: label anchoring and document assembly, with no OCR engine and no model.

Pages are hand-built PageOcr fixtures, so these run in milliseconds and are exactly
reproducible. That is a property of the design, not of the tests: CP15's extraction path
contains no model, so its behavior is fully determined by its input.
"""

import pytest
from chartwright_extract import anchor_field, extract_document
from chartwright_ocr import OcrToken, PageOcr, verify_at
from chartwright_schemas import BoundingBox
from chartwright_schemas.taxonomy import DocType


def tok(text: str, x: float, y: float, w: float = 90.0, h: float = 26.0, conf: float = 0.95):
    return OcrToken(text=text, bbox=BoundingBox(x=x, y=y, w=w, h=h), confidence=conf)


def page(*tokens: OcrToken) -> PageOcr:
    return PageOcr(width=1700, height=2200, tokens=tuple(tokens))


# A miniature PA form: label at x=90, value at x=600, one row per line.
def _form_page() -> PageOcr:
    return page(
        tok("Member", 90, 200),
        tok("Name:", 190, 200),
        tok("Avery", 600, 200),
        tok("Novak", 700, 200),
        tok("Member", 90, 260),
        tok("ID:", 190, 260),
        tok("A21743360", 600, 260),
        tok("Date", 90, 320),
        tok("of", 150, 320),
        tok("Birth:", 200, 320),
        tok("11/12/1999", 600, 320),
    )


class TestAnchorField:
    def test_reads_the_value_to_the_right_of_the_label(self) -> None:
        match = anchor_field(_form_page(), "Member ID")
        assert match is not None
        assert match.value == "A21743360"

    def test_bbox_covers_the_value_not_the_label(self) -> None:
        match = anchor_field(_form_page(), "Member ID")
        assert match is not None
        assert match.bbox.x >= 600  # label sits at x=90; the box must not include it

    def test_similar_labels_do_not_collide(self) -> None:
        """'Member ID' and 'Member Name' share a prefix; each must find its own row."""
        p = _form_page()
        assert anchor_field(p, "Member ID").value == "A21743360"  # type: ignore[union-attr]
        assert anchor_field(p, "Member Name").value == "Avery Novak"  # type: ignore[union-attr]

    def test_absent_label_returns_none_rather_than_a_guess(self) -> None:
        assert anchor_field(_form_page(), "Procedure (CPT)") is None

    def test_label_with_no_value_returns_none(self) -> None:
        assert anchor_field(page(tok("Member", 90, 200), tok("ID:", 190, 200)), "Member ID") is None

    def test_reads_the_line_below_when_nothing_is_to_the_right(self) -> None:
        p = page(
            tok("Clinical", 90, 400),
            tok("Justification:", 190, 400),
            tok("Patient", 95, 460),
            tok("with", 190, 460),
            tok("migraine", 280, 460),
        )
        match = anchor_field(p, "Clinical Justification")
        assert match is not None
        assert match.value.startswith("Patient with")

    def test_confidence_combines_label_and_token_scores(self) -> None:
        p = page(tok("Member", 90, 260), tok("ID:", 190, 260), tok("A217", 600, 260, conf=0.5))
        match = anchor_field(p, "Member ID")
        assert match is not None
        assert 0.0 <= match.confidence <= 1.0
        assert match.confidence == pytest.approx(match.label_score * 0.5)

    def test_empty_page_returns_none(self) -> None:
        assert anchor_field(page(), "Member ID") is None


class TestExtractDocument:
    def test_extracts_the_fields_the_page_supports(self) -> None:
        result = extract_document([_form_page()], DocType.PRIOR_AUTH_REQUEST, "d1")
        keys = {f.key for f in result.fields}
        assert {"member_id", "member_name", "member_dob"} <= keys

    def test_unfound_fields_are_absent_never_fabricated(self) -> None:
        """The core ADR-0003 contract: no anchor means no field, not an invented one."""
        result = extract_document([_form_page()], DocType.PRIOR_AUTH_REQUEST, "d1")
        keys = {f.key for f in result.fields}
        assert "procedure_code" not in keys  # nothing on the page supports it
        assert all(f.value_raw.strip() for f in result.fields)

    def test_every_emitted_field_verifies_at_its_own_provenance(self) -> None:
        """The mechanism gate: what we claim is there, is actually there."""
        p = _form_page()
        result = extract_document([p], DocType.PRIOR_AUTH_REQUEST, "d1")
        assert result.fields
        for f in result.fields:
            assert verify_at(p, f.value_raw, f.provenance.bbox), f"{f.key} failed verify_at"

    def test_provenance_records_the_page_the_value_came_from(self) -> None:
        blank = page(tok("Continuation", 90, 100))
        result = extract_document([blank, _form_page()], DocType.PRIOR_AUTH_REQUEST, "d1")
        member_id = next(f for f in result.fields if f.key == "member_id")
        assert member_id.provenance.page == 2
        assert result.page_count == 2

    def test_extraction_is_deterministic(self) -> None:
        a = extract_document([_form_page()], DocType.PRIOR_AUTH_REQUEST, "d1")
        b = extract_document([_form_page()], DocType.PRIOR_AUTH_REQUEST, "d1")
        assert [(f.key, f.value_raw, f.confidence) for f in a.fields] == [
            (f.key, f.value_raw, f.confidence) for f in b.fields
        ]

    def test_type_without_a_schema_yields_no_fields(self) -> None:
        result = extract_document([_form_page()], DocType.CLINICAL_NOTE, "d1")
        assert result.fields == []

    def test_no_pages_is_an_upstream_bug_and_raises(self) -> None:
        with pytest.raises(ValueError, match="no OCR pages"):
            extract_document([], DocType.PRIOR_AUTH_REQUEST, "d1")

    def test_normalized_values_are_left_for_cp16(self) -> None:
        result = extract_document([_form_page()], DocType.PRIOR_AUTH_REQUEST, "d1")
        assert all(f.value_normalized is None for f in result.fields)
        assert all(f.code_system is None for f in result.fields)
