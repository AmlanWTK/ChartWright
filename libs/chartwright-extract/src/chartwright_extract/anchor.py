"""Deterministic label-anchored field extraction (CP15, ADR-0011).

These are forms. ``FieldSpec.label`` holds the label as printed on the page, and the value
sits beside it or beneath it. Finding the label in the OCR tokens and reading the run of
tokens next to it extracts the field exactly, with pixel-accurate grounding, and without
a model.

That is not a shortcut around the AI core, it is the bottom rung of ADR-0002's cost-aware
cascade: route each page to the cheapest thing that can handle it, and free-and-
deterministic is cheaper than Tier-0. CP15's Phase 0 spike measured the alternative --
per-field VLM prompting scored **0/24 groundable** against this approach's **24/24
grounded, 23/24 correct** -- so the model does not enter the extraction path at all. VLM
escalation for fields the anchor cannot find belongs to CP17's escalation cascade.

**What this does NOT protect against.** Grounding proves that text is at that location. It
does not prove the OCR read it correctly: the spike's single miss was ``Drew Iyer`` read
as ``Drew lyer``, correctly located and confidently wrong. A grounded field is not a
verified field -- that is CP16's job (validation, code systems) and CP17's (calibration).
"""

from __future__ import annotations

from dataclasses import dataclass

from chartwright_ocr import OcrToken, PageOcr, similarity
from chartwright_schemas import BoundingBox

# How well the printed label must match before we trust the anchor. Too low and a field
# that is absent from the page latches onto a different label's row; too high and OCR
# noise on the label defeats an otherwise readable value. Measured by scripts/eval_extract.py.
MIN_LABEL_SCORE = 0.75

# Labels are 1-3 tokens on these forms ("Member ID", "Diagnosis Code (ICD-10)").
_MAX_LABEL_TOKENS = 4
# A value is at most this many tokens; beyond it we are almost certainly reading the next
# field's label rather than this field's value.
_MAX_VALUE_TOKENS = 8


@dataclass(frozen=True)
class AnchorMatch:
    """A field value located by its printed label."""

    value: str
    bbox: BoundingBox
    label_score: float  # [0,1] similarity of the matched label text to the expected label
    token_confidence: float  # [0,1] mean engine confidence over the value tokens

    @property
    def confidence(self) -> float:
        """Derived, UNCALIBRATED confidence (see module docstring; CP17 owns the real one).

        Both factors matter and neither dominates: a crisp label over mush is as suspect
        as mush next to a confident value.
        """
        return max(0.0, min(1.0, self.label_score * self.token_confidence))


def _envelope(tokens: list[OcrToken]) -> BoundingBox:
    x0 = min(t.bbox.x for t in tokens)
    y0 = min(t.bbox.y for t in tokens)
    x1 = max(t.bbox.x + t.bbox.w for t in tokens)
    y1 = max(t.bbox.y + t.bbox.h for t in tokens)
    return BoundingBox(x=x0, y=y0, w=max(x1 - x0, 1.0), h=max(y1 - y0, 1.0))


def _centre_y(token: OcrToken) -> float:
    return token.bbox.y + token.bbox.h / 2


def _find_label(tokens: list[OcrToken], label: str, min_score: float) -> tuple[int, int, float]:
    """Best-scoring window of consecutive tokens matching ``label``.

    Returns ``(start, end, score)``; ``start`` is -1 when nothing clears ``min_score``.
    Best-wins matters on real schemas: "Member ID" and "Member Name" share a prefix, and
    the higher-scoring window is the right one.
    """
    best_start, best_end, best_score = -1, -1, 0.0
    for i in range(len(tokens)):
        for size in range(1, _MAX_LABEL_TOKENS + 1):
            window = tokens[i : i + size]
            if len(window) < size:
                break
            score = similarity(" ".join(t.text for t in window), label)
            if score > best_score:
                best_start, best_end, best_score = i, i + size, score
    if best_score < min_score:
        return -1, -1, best_score
    return best_start, best_end, best_score


def _value_to_the_right(tokens: list[OcrToken], label_end: int, anchor: OcrToken) -> list[OcrToken]:
    """Tokens following the label whose vertical centre stays within the label's band."""
    top = anchor.bbox.y - anchor.bbox.h * 0.6
    bottom = anchor.bbox.y + anchor.bbox.h * 1.6
    out: list[OcrToken] = []
    for token in tokens[label_end : label_end + _MAX_VALUE_TOKENS]:
        if top <= _centre_y(token) <= bottom:
            out.append(token)
        else:
            break
    return out


def _value_below(tokens: list[OcrToken], label_end: int, anchor: OcrToken) -> list[OcrToken]:
    """Tokens on the next line down that horizontally overlap the label.

    Forms use both layouts; a label with nothing to its right usually has its value
    underneath (section headers, free-text boxes).
    """
    below = [t for t in tokens[label_end:] if _centre_y(t) > anchor.bbox.y + anchor.bbox.h]
    if not below:
        return []
    line_y = _centre_y(below[0])
    band = max(below[0].bbox.h, 1.0) * 0.8
    label_left, label_right = anchor.bbox.x, anchor.bbox.x + anchor.bbox.w * 3
    out: list[OcrToken] = []
    for token in below[:_MAX_VALUE_TOKENS]:
        if abs(_centre_y(token) - line_y) > band:
            break
        if token.bbox.x + token.bbox.w >= label_left and token.bbox.x <= label_right:
            out.append(token)
    return out


def anchor_field(
    page: PageOcr, label: str, *, min_label_score: float = MIN_LABEL_SCORE
) -> AnchorMatch | None:
    """Locate ``label`` on the page and read the value next to it.

    Returns ``None`` when the label cannot be found or carries no value tokens. The caller
    must NOT invent a value in that case -- an absent field is the correct, auditable
    outcome (ADR-0003), and how often it happens is the metric that sizes CP17's cascade.
    """
    tokens = list(page.tokens)
    if not tokens or not label.strip():
        return None

    start, end, score = _find_label(tokens, label, min_label_score)
    if start < 0:
        return None

    anchor = tokens[start]
    value_tokens = _value_to_the_right(tokens, end, anchor) or _value_below(tokens, end, anchor)
    value = " ".join(t.text for t in value_tokens).strip()
    if not value_tokens or not value:
        return None

    mean_conf = sum(t.confidence for t in value_tokens) / len(value_tokens)
    return AnchorMatch(
        value=value,
        bbox=_envelope(value_tokens),
        label_score=score,
        token_confidence=max(0.0, min(1.0, mean_conf)),
    )
