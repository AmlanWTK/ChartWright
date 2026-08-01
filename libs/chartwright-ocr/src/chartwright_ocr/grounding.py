"""Grounding: locate a value's physical evidence on the page, or refuse to ground it.

This is ADR-0003's enforcement mechanism. Given a candidate value (from any source —
OCR itself, a VLM extractor in CP15, or a reviewer), ``locate_value`` finds where on the
page that value actually appears and returns the covering bbox + a match score. A value
that cannot be located does NOT get invented coordinates — it gets ``None``, which
downstream treats as "unverified" (confidence penalty / review routing).

Matching is fuzzy (OCR noise-tolerant): text is normalized (case, punctuation-light,
whitespace-collapsed) and compared with a similarity ratio; values may span multiple
adjacent tokens on a line.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from chartwright_schemas import BoundingBox

from chartwright_ocr.engine import OcrToken, PageOcr


def normalize(text: str) -> str:
    """Noise-tolerant canonical form: lowercase, collapse spaces, strip most punctuation."""
    text = text.lower()
    text = re.sub(r"[^\w./:\-@ ]+", "", text)  # keep chars meaningful in IDs/dates/phones
    text = re.sub(r"\s+", " ", text).strip()
    # Punctuation is only meaningful *inside* a token ("03/14/1985", "14:30", "a-1");
    # at a token edge it is label noise ("Member ID:") and must not defeat a match.
    return " ".join(w.strip("./:-@") for w in text.split())


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


@dataclass(frozen=True)
class GroundingMatch:
    bbox: BoundingBox
    matched_text: str
    score: float  # [0,1] similarity of matched span vs. the value


def _envelope(tokens: list[OcrToken]) -> BoundingBox:
    x0 = min(t.bbox.x for t in tokens)
    y0 = min(t.bbox.y for t in tokens)
    x1 = max(t.bbox.x + t.bbox.w for t in tokens)
    y1 = max(t.bbox.y + t.bbox.h for t in tokens)
    return BoundingBox(x=x0, y=y0, w=max(x1 - x0, 1.0), h=max(y1 - y0, 1.0))


def locate_value(page: PageOcr, value: str, *, min_score: float = 0.75) -> GroundingMatch | None:
    """Find the best window of 1..4 consecutive tokens matching ``value``.

    Consecutive-in-reading-order windows approximate "adjacent on the page" because the
    engine emits tokens line-by-line. Returns the best match at/above ``min_score``,
    else None (the caller must NOT fabricate a location).
    """
    tokens = list(page.tokens)
    if not tokens or not value.strip():
        return None

    best: GroundingMatch | None = None
    max_window = 4
    for start in range(len(tokens)):
        for size in range(1, max_window + 1):
            window = tokens[start : start + size]
            if len(window) < size:
                break
            candidate = " ".join(t.text for t in window)
            score = similarity(candidate, value)
            if score >= min_score and (best is None or score > best.score):
                best = GroundingMatch(bbox=_envelope(window), matched_text=candidate, score=score)
        if best is not None and best.score >= 0.999:
            break  # cannot beat an exact match
    return best


def verify_at(page: PageOcr, value: str, claimed: BoundingBox, *, min_score: float = 0.75) -> bool:
    """Does ``value`` actually appear within/near the ``claimed`` region?

    Used to audit third-party claims (e.g. a VLM extractor asserting a location in
    CP15): collect tokens overlapping the claimed box and fuzzy-match their text.
    """
    overlapping = [t for t in page.tokens if _overlaps(t.bbox, claimed)]
    if not overlapping:
        return False
    region_text = " ".join(t.text for t in overlapping)
    return similarity(region_text, value) >= min_score or normalize(value) in normalize(region_text)


def _overlaps(a: BoundingBox, b: BoundingBox) -> bool:
    return not (a.x + a.w < b.x or b.x + b.w < a.x or a.y + a.h < b.y or b.y + b.h < a.y)
