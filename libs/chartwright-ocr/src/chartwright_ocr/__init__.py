"""chartwright-ocr: Tier-0 OCR with grounding (CP12, ADR-0003)."""

from chartwright_ocr.engine import OcrEngine, OcrToken, PageOcr, RapidOcrEngine
from chartwright_ocr.grounding import (
    GroundingMatch,
    locate_value,
    normalize,
    similarity,
    verify_at,
)
from chartwright_ocr.serialization import page_ocr_from_json, page_ocr_to_json

__all__ = [
    "GroundingMatch",
    "OcrEngine",
    "OcrToken",
    "PageOcr",
    "RapidOcrEngine",
    "locate_value",
    "normalize",
    "page_ocr_from_json",
    "page_ocr_to_json",
    "similarity",
    "verify_at",
]

__version__ = "0.1.0"
