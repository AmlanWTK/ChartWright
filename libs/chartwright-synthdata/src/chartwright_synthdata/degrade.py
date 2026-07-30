"""Fax-style degradation with label-preserving geometry.

Pixel-local effects (noise, contrast, threshold) never move ink, so bboxes stay valid.
Skew is the only geometric transform; we rotate the image AND transform every bbox with
the same rotation so labels remain pixel-accurate at every degradation level.
"""

from __future__ import annotations

import math
import random
from enum import StrEnum

from chartwright_schemas import BoundingBox, ExtractionResult, GroundedField, Provenance
from PIL import Image, ImageEnhance


class Degradation(StrEnum):
    """Difficulty slices measured separately by the eval harness (CP26)."""

    CLEAN = "clean"  # 300-DPI-scan quality; Tier-0 territory
    FAX = "fax"  # typical fax: mild noise, slight skew, binarized
    BAD_FAX = "bad_fax"  # the hard slice: heavy noise, skew, low contrast


def _add_noise(img: Image.Image, rng: random.Random, amount: float) -> Image.Image:
    """Salt-and-pepper noise; pixel-local, geometry-preserving."""
    if amount <= 0:
        return img
    px = img.load()
    if px is None:  # pragma: no cover - load() only returns None for deferred/unloaded images
        return img
    w, h = img.size
    n_pixels = int(w * h * amount)
    for _ in range(n_pixels):
        x, y = rng.randrange(w), rng.randrange(h)
        px[x, y] = 0 if rng.random() < 0.5 else 255
    return img


def _rotate_bbox(
    bbox: BoundingBox,
    angle_deg: float,
    center: tuple[float, float],
    expand_offset: tuple[float, float],
) -> BoundingBox:
    """Axis-aligned bbox of the rotated original box (same transform PIL applies).

    PIL's Image.rotate(angle) rotates counter-clockwise about the center; with expand=True
    the canvas grows and content shifts by ``expand_offset``. We rotate the box corners with
    the same math and take their axis-aligned envelope.
    """
    theta = math.radians(angle_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    cx, cy = center
    corners = [
        (bbox.x, bbox.y),
        (bbox.x + bbox.w, bbox.y),
        (bbox.x, bbox.y + bbox.h),
        (bbox.x + bbox.w, bbox.y + bbox.h),
    ]
    xs: list[float] = []
    ys: list[float] = []
    for x, y in corners:
        dx, dy = x - cx, y - cy
        # Image y-axis points down, so CCW image rotation is CW in math coords:
        rx = cx + dx * cos_t + dy * sin_t
        ry = cy - dx * sin_t + dy * cos_t
        xs.append(rx + expand_offset[0])
        ys.append(ry + expand_offset[1])
    x0, y0 = max(min(xs), 0.0), max(min(ys), 0.0)
    return BoundingBox(x=x0, y=y0, w=max(max(xs) - x0, 1.0), h=max(max(ys) - y0, 1.0))


def degrade(
    img: Image.Image,
    labels: ExtractionResult,
    level: Degradation,
    seed: int,
) -> tuple[Image.Image, ExtractionResult]:
    """Apply the degradation level; return (new_image, labels with transformed bboxes)."""
    if level is Degradation.CLEAN:
        return img, labels

    rng = random.Random(seed)  # noqa: S311 - non-cryptographic use is intentional
    out = img.copy()

    if level is Degradation.FAX:
        angle = rng.uniform(-1.0, 1.0)
        noise = 0.004
        contrast = 0.9
    else:  # BAD_FAX
        angle = rng.uniform(-3.5, 3.5)
        noise = 0.02
        contrast = 0.6

    # 1) Contrast (pixel-local)
    out = ImageEnhance.Contrast(out).enhance(contrast)

    # 2) Skew via rotation (geometric — transform bboxes identically)
    w0, h0 = out.size
    center = (w0 / 2.0, h0 / 2.0)
    out = out.rotate(angle, expand=True, fillcolor=255, resample=Image.Resampling.BILINEAR)
    w1, h1 = out.size
    expand_offset = ((w1 - w0) / 2.0, (h1 - h0) / 2.0)

    new_fields = [
        GroundedField(
            key=f.key,
            value_raw=f.value_raw,
            value_normalized=f.value_normalized,
            code_system=f.code_system,
            confidence=f.confidence,
            provenance=Provenance(
                page=f.provenance.page,
                bbox=_rotate_bbox(f.provenance.bbox, angle, center, expand_offset),
                source_span=f.provenance.source_span,
            ),
            needs_review=f.needs_review,
            tier=f.tier,
        )
        for f in labels.fields
    ]

    # 3) Noise, then binarize for fax feel (pixel-local)
    out = _add_noise(out, rng, noise)
    if level is Degradation.FAX:
        out = out.point(lambda p: 255 if p > 160 else 0)

    new_labels = labels.model_copy(update={"fields": new_fields})
    return out, new_labels
