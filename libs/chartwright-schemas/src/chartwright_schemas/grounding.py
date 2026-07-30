"""The grounding contract (ADR-0003).

Every value extracted from a document must be traceable to a physical location on a page
(bounding box + source span) and carry a calibrated confidence. These types make that
contract structural: an AI stage physically cannot emit an ungrounded field.

Coordinate convention: pixels, origin at top-left of the page image, ``bbox = (x, y, w, h)``.
"""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

# Confidence is always calibrated to [0, 1] (target ECE <= 0.05, enforced from CP17).
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class BoundingBox(BaseModel):
    """Axis-aligned box on a page image, in pixels, origin top-left."""

    model_config = ConfigDict(frozen=True)

    x: Annotated[float, Field(ge=0)]
    y: Annotated[float, Field(ge=0)]
    w: Annotated[float, Field(gt=0)]
    h: Annotated[float, Field(gt=0)]

    def as_tuple(self) -> tuple[float, float, float, float]:
        return (self.x, self.y, self.w, self.h)


class Provenance(BaseModel):
    """Where a value physically came from: page + region + the literal source text."""

    model_config = ConfigDict(frozen=True)

    page: Annotated[int, Field(ge=1, description="1-based page number within the document")]
    bbox: BoundingBox
    source_span: str = Field(
        min_length=1,
        description="The literal text at the bbox that supports the extracted value.",
    )


class GroundedField(BaseModel):
    """A single extracted field with mandatory provenance and confidence.

    ``value_raw`` is exactly what appears in the document; ``value_normalized`` is the
    canonical form (e.g. ICD-10 uppercase dotted, ISO dates) produced by validation (CP16).
    A field with no supporting text in the document must be *absent*, never fabricated.
    """

    key: str = Field(min_length=1, description="Schema field key, e.g. 'member_id'.")
    value_raw: str = Field(min_length=1)
    value_normalized: str | None = Field(
        default=None, description="Canonical form after validation/normalization (CP16)."
    )
    code_system: str | None = Field(
        default=None, description="Code system for normalized value: ICD10 | CPT | NPI | ..."
    )
    confidence: Confidence
    provenance: Provenance
    needs_review: bool = Field(
        default=False, description="True when confidence is below the routing threshold."
    )
    tier: Annotated[int, Field(ge=0, le=2)] = Field(
        default=0, description="Model tier that produced this value (0 self-host, 2 frontier)."
    )


class GroundedCell(BaseModel):
    """One table cell with its own grounding."""

    row: Annotated[int, Field(ge=0)]
    col: Annotated[int, Field(ge=0)]
    text: str
    confidence: Confidence
    bbox: BoundingBox


class GroundedTable(BaseModel):
    """An extracted table preserving row/column structure (labs, EOB lines, med lists)."""

    key: str = Field(min_length=1, description="Schema table key, e.g. 'requested_services'.")
    page: Annotated[int, Field(ge=1)]
    bbox: BoundingBox
    n_rows: Annotated[int, Field(ge=1)]
    n_cols: Annotated[int, Field(ge=1)]
    cells: list[GroundedCell] = Field(min_length=1)
    confidence: Confidence

    @model_validator(mode="after")
    def _cells_within_declared_shape(self) -> GroundedTable:
        for cell in self.cells:
            if cell.row >= self.n_rows or cell.col >= self.n_cols:
                msg = (
                    f"cell ({cell.row},{cell.col}) outside declared shape "
                    f"{self.n_rows}x{self.n_cols} for table '{self.key}'"
                )
                raise ValueError(msg)
        return self
