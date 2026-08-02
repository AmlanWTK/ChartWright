"""Page-level image normalization: orientation, skew, contrast — geometry only.

Every transform records its parameters on the returned ``NormalizedPage`` so a caller
can map a location on the normalized page back to the original, the same discipline
``chartwright_synthdata.degrade`` uses for its (inverse) transforms: never move ink
silently. Field-value normalization (dates, phone numbers, code systems) is CP16's
job, not this module's — this module only ever touches pixels and page geometry.

No OCR, no VLM, no model gateway calls: orientation and skew are recovered from pure
image statistics (projection profiles), which is why this can run before CLASSIFIED/
OCR_DONE in the pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image, ImageEnhance

# Candidate deskew angles, degrees. Kept narrow: coarse orientation (0/90/180/270) is
# handled separately, so fine deskew only needs to correct realistic scan/fax tilt.
_DESKEW_RANGE_DEG = 5.0
_DESKEW_STEP_DEG = 0.25


@dataclass(frozen=True)
class NormalizedPage:
    """A normalized page plus the transform parameters needed to recover geometry."""

    image: Image.Image
    rotation_deg: int  # coarse orientation correction applied: one of 0/90/180/270
    skew_angle_deg: float  # fine deskew applied, degrees (positive = counter-clockwise)
    contrast_factor: float  # PIL ImageEnhance.Contrast factor applied


def _to_gray_array(img: Image.Image) -> np.ndarray:
    if img.mode != "L":
        img = img.convert("L")
    return np.asarray(img, dtype=np.float64)


def _row_projection_variance(arr: np.ndarray) -> float:
    """Variance of the row-sum (horizontal) ink profile.

    Text set on horizontal lines produces a strongly periodic row profile (line rows are
    dark, gaps are light); the same page rotated 90 degrees loses that periodicity because
    ink is smeared across rows instead of concentrated in line-bands. This is the standard
    projection-profile heuristic for text-orientation detection, requiring no OCR.
    """
    row_sums = arr.sum(axis=1)
    return float(np.var(row_sums))


def _upper_lower_asymmetry(arr: np.ndarray, *, ink_threshold: float = 200.0) -> float:
    """How much more ink sits in the upper half of text-line bands than the lower half.

    Latin text has more ink above the baseline (x-height + ascenders) than below it
    (descenders on a minority of glyphs). Correctly-oriented text therefore scores
    positive; text upside down (180 degrees) scores negative. Used only to break the
    0-vs-180 tie left by the row-projection axis test.
    """
    ink = arr < ink_threshold  # dark pixels
    row_ink = ink.sum(axis=1).astype(np.float64)
    if row_ink.sum() == 0:
        return 0.0
    # Identify line bands as runs of rows with above-median ink, then split each
    # band at its vertical midpoint and compare halves.
    threshold = max(float(np.median(row_ink[row_ink > 0])), 1.0) * 0.3
    is_line = row_ink > threshold
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for i, v in enumerate(is_line):
        if v and start is None:
            start = i
        elif not v and start is not None:
            bands.append((start, i))
            start = None
    if start is not None:
        bands.append((start, len(is_line)))

    score = 0.0
    counted = 0
    for lo, hi in bands:
        if hi - lo < 4:  # too thin to split meaningfully
            continue
        mid = (lo + hi) // 2
        upper = row_ink[lo:mid].sum()
        lower = row_ink[mid:hi].sum()
        total = upper + lower
        if total <= 0:
            continue
        score += (upper - lower) / total
        counted += 1
    return score / counted if counted else 0.0


def detect_orientation(img: Image.Image) -> int:
    """Return the rotation (degrees, counter-clockwise) needed to correct ``img``.

    Two-stage: pick the axis (0/180 vs 90/270) by row-projection variance, then within
    that axis pick the specific orientation by upper/lower ink asymmetry.
    """
    candidates = (0, 90, 180, 270)
    axis_scores: dict[int, float] = {}
    for angle in candidates:
        rotated = img.rotate(-angle, expand=True) if angle else img
        axis_scores[angle] = _row_projection_variance(_to_gray_array(rotated))

    best_axis = (
        (0, 180)
        if axis_scores[0] + axis_scores[180] >= axis_scores[90] + axis_scores[270]
        else (90, 270)
    )

    # Empirically (measured against the synthetic generator's rendered glyphs), the
    # correctly-oriented page scores *lower* upper/lower asymmetry than its 180-degree
    # flip, not higher — so the tie-break minimizes, not maximizes, this score.
    best_angle = best_axis[0]
    best_asym = None
    for angle in best_axis:
        rotated = img.rotate(-angle, expand=True) if angle else img
        asym = _upper_lower_asymmetry(_to_gray_array(rotated))
        if best_asym is None or asym < best_asym:
            best_asym = asym
            best_angle = angle
    return best_angle


def detect_skew(img: Image.Image) -> float:
    """Fine deskew angle (degrees) that maximizes row-projection variance.

    Assumes coarse orientation has already been corrected — this only searches a narrow
    range around 0 degrees, matching realistic scan/fax tilt (see
    ``chartwright_synthdata.degrade``, whose slices apply comparable angles).
    """
    best_angle = 0.0
    best_score = -1.0
    angle = -_DESKEW_RANGE_DEG
    while angle <= _DESKEW_RANGE_DEG:
        rotated = img.rotate(angle, expand=False, fillcolor=255, resample=Image.Resampling.BILINEAR)
        score = _row_projection_variance(_to_gray_array(rotated))
        if score > best_score:
            best_score = score
            best_angle = angle
        angle += _DESKEW_STEP_DEG
    return best_angle


def normalize_page(img: Image.Image, *, contrast_factor: float = 1.3) -> NormalizedPage:
    """Correct orientation, deskew, and normalize contrast. Geometry stays recoverable.

    ``contrast_factor`` > 1 counteracts the low-contrast end of CP12's degradation range
    (bad_fax uses contrast=0.52); it is a fixed, deterministic boost, not adaptive, so the
    transform is always known and reversible in spirit even though PIL doesn't give us a
    literal inverse.
    """
    rotation = detect_orientation(img)
    oriented = img.rotate(-rotation, expand=True) if rotation else img

    skew = detect_skew(oriented)
    deskewed = (
        oriented.rotate(skew, expand=False, fillcolor=255, resample=Image.Resampling.BILINEAR)
        if skew
        else oriented
    )

    normalized = ImageEnhance.Contrast(deskewed).enhance(contrast_factor)

    return NormalizedPage(
        image=normalized,
        rotation_deg=rotation,
        skew_angle_deg=skew,
        contrast_factor=contrast_factor,
    )
