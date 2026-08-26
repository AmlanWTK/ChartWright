"""chartwright-extract: deterministic label-anchored field extraction (CP15, ADR-0011)."""

from chartwright_extract.anchor import MIN_LABEL_SCORE, AnchorMatch, anchor_field
from chartwright_extract.extractor import extract_document

__all__ = [
    "MIN_LABEL_SCORE",
    "AnchorMatch",
    "anchor_field",
    "extract_document",
]

__version__ = "0.1.0"
