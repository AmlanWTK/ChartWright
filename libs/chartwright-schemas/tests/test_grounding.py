"""Tests for the grounding contract types."""

import pytest
from chartwright_schemas import (
    BoundingBox,
    GroundedCell,
    GroundedField,
    GroundedTable,
    Provenance,
)
from pydantic import ValidationError


def make_provenance(page: int = 1) -> Provenance:
    return Provenance(
        page=page,
        bbox=BoundingBox(x=10, y=20, w=100, h=18),
        source_span="Member ID: A1234567",
    )


class TestBoundingBox:
    def test_valid_box(self) -> None:
        box = BoundingBox(x=0, y=0, w=50, h=10)
        assert box.as_tuple() == (0, 0, 50, 10)

    def test_zero_size_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BoundingBox(x=0, y=0, w=0, h=10)

    def test_negative_origin_rejected(self) -> None:
        with pytest.raises(ValidationError):
            BoundingBox(x=-1, y=0, w=10, h=10)

    def test_immutable(self) -> None:
        box = BoundingBox(x=1, y=1, w=5, h=5)
        with pytest.raises(ValidationError):
            box.x = 99  # type: ignore[misc]


class TestGroundedField:
    def test_valid_field(self) -> None:
        f = GroundedField(
            key="member_id",
            value_raw="A1234567",
            confidence=0.94,
            provenance=make_provenance(),
        )
        assert f.needs_review is False
        assert f.tier == 0

    def test_confidence_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GroundedField(
                key="member_id",
                value_raw="A1234567",
                confidence=1.5,
                provenance=make_provenance(),
            )

    def test_provenance_is_mandatory(self) -> None:
        """The grounding contract: a field without provenance cannot exist."""
        with pytest.raises(ValidationError):
            GroundedField(key="member_id", value_raw="A1234567", confidence=0.9)  # type: ignore[call-arg]

    def test_empty_value_rejected(self) -> None:
        with pytest.raises(ValidationError):
            GroundedField(
                key="member_id", value_raw="", confidence=0.9, provenance=make_provenance()
            )

    def test_tier_bounds(self) -> None:
        with pytest.raises(ValidationError):
            GroundedField(
                key="member_id",
                value_raw="A1234567",
                confidence=0.9,
                provenance=make_provenance(),
                tier=3,
            )


class TestGroundedTable:
    def _cell(self, row: int, col: int) -> GroundedCell:
        return GroundedCell(
            row=row, col=col, text="x", confidence=0.9, bbox=BoundingBox(x=0, y=0, w=5, h=5)
        )

    def test_valid_table(self) -> None:
        t = GroundedTable(
            key="claim_lines",
            page=1,
            bbox=BoundingBox(x=0, y=0, w=500, h=200),
            n_rows=2,
            n_cols=2,
            cells=[self._cell(0, 0), self._cell(1, 1)],
            confidence=0.9,
        )
        assert t.n_rows == 2

    def test_cell_outside_shape_rejected(self) -> None:
        with pytest.raises(ValidationError, match="outside declared shape"):
            GroundedTable(
                key="claim_lines",
                page=1,
                bbox=BoundingBox(x=0, y=0, w=500, h=200),
                n_rows=2,
                n_cols=2,
                cells=[self._cell(5, 0)],
                confidence=0.9,
            )
