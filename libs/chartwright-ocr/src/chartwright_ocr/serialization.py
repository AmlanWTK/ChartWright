"""Persist a ``PageOcr`` between pipeline stages.

CP12 produced OCR in memory; CP15 needs it to survive from the ``OCR_DONE`` stage to the
``EXTRACTED`` stage, which are separate Temporal activities and may run on different
workers. Object storage carries it -- deliberately not a new table, since OCR output is
bulky, page-shaped and reproducible, exactly like the normalized page images CP13 already
stores that way. No schema change.

The format is plain JSON rather than a pickle: it is inspectable during debugging, and a
future engine swap (vLLM-served dots.ocr at the cloud re-entry) has to satisfy a written
contract rather than whatever a dataclass happened to look like that day.
"""

from __future__ import annotations

import json
from typing import Any

from chartwright_schemas import BoundingBox

from chartwright_ocr.engine import OcrToken, PageOcr


def page_ocr_to_json(page: PageOcr) -> bytes:
    """Serialize a page's OCR result to compact UTF-8 JSON."""
    payload = {
        "width": page.width,
        "height": page.height,
        "tokens": [
            {
                "text": t.text,
                "bbox": {"x": t.bbox.x, "y": t.bbox.y, "w": t.bbox.w, "h": t.bbox.h},
                "confidence": t.confidence,
            }
            for t in page.tokens
        ],
    }
    return json.dumps(payload, separators=(",", ":")).encode("utf-8")


def page_ocr_from_json(data: bytes | str) -> PageOcr:
    """Rebuild a ``PageOcr``. Raises on malformed input rather than returning a partial page.

    A truncated or corrupt OCR blob is an infrastructure fault, not a document-quality
    problem: silently yielding fewer tokens would show up downstream as a document that
    mysteriously extracts badly, which is far harder to diagnose than a loud failure here.
    """
    payload: Any = json.loads(data)
    if not isinstance(payload, dict):
        msg = "OCR payload is not an object"
        raise ValueError(msg)
    tokens = tuple(
        OcrToken(
            text=str(t["text"]),
            bbox=BoundingBox(**t["bbox"]),
            confidence=float(t["confidence"]),
        )
        for t in payload["tokens"]
    )
    return PageOcr(width=int(payload["width"]), height=int(payload["height"]), tokens=tokens)
