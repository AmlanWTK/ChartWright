"""OCR engines: the protocol + the RapidOCR adapter (local Tier-0).

Design (extends ADR-0008): the grounding contract requires *pixel locations*, which
small local VLMs cannot reliably produce. Tier-0 therefore uses a deterministic OCR
engine that returns per-token text + bounding box + confidence; VLMs handle semantics
downstream (CP14/CP15). Production swaps RapidOCR for vLLM-served layout VLMs behind
this same protocol.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Protocol

from PIL import Image

from chartwright_schemas import BoundingBox


@dataclass(frozen=True)
class OcrToken:
    """One recognized text span with its physical location."""

    text: str
    bbox: BoundingBox
    confidence: float  # engine-reported, [0,1]


@dataclass(frozen=True)
class PageOcr:
    """Everything the engine read on one page, in reading order."""

    width: int
    height: int
    tokens: tuple[OcrToken, ...]

    @property
    def full_text(self) -> str:
        return "\n".join(t.text for t in self.tokens)


class OcrEngine(Protocol):
    name: str

    def recognize(self, image_bytes: bytes) -> PageOcr: ...


def _quad_to_bbox(quad: list[list[float]]) -> BoundingBox:
    """RapidOCR returns 4-point quads; grounding uses axis-aligned envelopes."""
    xs = [p[0] for p in quad]
    ys = [p[1] for p in quad]
    x0, y0 = max(min(xs), 0.0), max(min(ys), 0.0)
    return BoundingBox(x=x0, y=y0, w=max(max(xs) - x0, 1.0), h=max(max(ys) - y0, 1.0))


class RapidOcrEngine:
    """RapidOCR (ONNX PaddleOCR models): pip-installable, CPU-only, real boxes.

    The model loads lazily on first use (~a few seconds) and is reused thereafter.
    Tokens are sorted into natural reading order: top-to-bottom lines, left-to-right
    within a line (line = vertical-center proximity).
    """

    def __init__(self) -> None:
        self.name = "rapidocr"
        self._engine: Any | None = None

    def _get_engine(self) -> Any:
        if self._engine is None:
            from rapidocr_onnxruntime import RapidOCR  # heavy import deferred

            self._engine = RapidOCR()
        return self._engine

    def recognize(self, image_bytes: bytes) -> PageOcr:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        width, height = image.size

        import numpy as np

        result, _ = self._get_engine()(np.asarray(image))
        raw: list[OcrToken] = []
        for quad, text, score in result or []:
            if not str(text).strip():
                continue
            raw.append(
                OcrToken(
                    text=str(text),
                    bbox=_quad_to_bbox(quad),
                    confidence=max(0.0, min(float(score), 1.0)),
                )
            )
        return PageOcr(width=width, height=height, tokens=tuple(_reading_order(raw)))


def _reading_order(tokens: list[OcrToken]) -> list[OcrToken]:
    """Sort tokens top-to-bottom, grouping into lines by vertical-center proximity."""
    if not tokens:
        return []
    remaining = sorted(tokens, key=lambda t: t.bbox.y)
    lines: list[list[OcrToken]] = []
    for token in remaining:
        center = token.bbox.y + token.bbox.h / 2
        placed = False
        for line in lines:
            ref = line[0]
            ref_center = ref.bbox.y + ref.bbox.h / 2
            if abs(center - ref_center) <= max(ref.bbox.h, token.bbox.h) * 0.6:
                line.append(token)
                placed = True
                break
        if not placed:
            lines.append([token])
    ordered: list[OcrToken] = []
    for line in lines:
        ordered.extend(sorted(line, key=lambda t: t.bbox.x))
    return ordered
