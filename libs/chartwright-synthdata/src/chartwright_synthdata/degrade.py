"""Fax-style degradation with label-preserving geometry.

Pixel-local effects (noise, contrast, blur, threshold) never move ink, so bboxes stay
valid. Resolution loss is applied as a *net-identity* resample — downsample then restore
the original dimensions — which destroys detail exactly like a fax scan while leaving
every coordinate unchanged. Skew is therefore still the only transform that moves ink;
we rotate the image AND transform every bbox with the same rotation, so labels remain
pixel-accurate at every degradation level.

Resolution loss is the dominant artifact of a real fax (Group 3 halves vertical
resolution to ~98 DPI) and is what actually separates the difficulty slices; contrast
and salt-and-pepper noise alone leave modern OCR essentially unharmed.
"""

from __future__ import annotations

import math
import random
from enum import StrEnum

from chartwright_schemas import BoundingBox, ExtractionResult, GroundedField, Provenance
from PIL import Image, ImageEnhance, ImageFilter


class Degradation(StrEnum):
    """Difficulty slices measured separately by the eval harness (CP26)."""

    CLEAN = "clean"  # 300-DPI-scan quality; Tier-0 territory
    FAX = "fax"  # typical fax: halved vertical resolution, mild blur/noise/skew
    BAD_FAX = "bad_fax"  # the hard slice: severe resolution loss, blur, noise, skew


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


def _resolution_loss(img: Image.Image, fx: float, fy: float) -> Image.Image:
    """Downsample to (fx, fy) of size then restore — detail is lost, geometry is not.

    A real fax digitises at ~204x98 DPI, so vertical detail suffers far more than
    horizontal; ``fy < fx`` reproduces that anisotropy. Because the image is resampled
    back to its original dimensions, every bounding box remains exactly valid.
    """
    if fx >= 1.0 and fy >= 1.0:
        return img
    w, h = img.size
    small = img.resize((max(int(w * fx), 1), max(int(h * fy), 1)), Image.Resampling.BILINEAR)
    return small.resize((w, h), Image.Resampling.BILINEAR)


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

    # Calibrated empirically against the Tier-0 engine so each slice carries signal:
    # clean ~100% / fax ~99% / bad_fax ~79% field recall. Recognition degrades very
    # non-linearly in scale_y — 0.34 vs 0.31 is the difference between a hard slice and
    # an unreadable one — so change these deliberately and re-run scripts/eval_ocr.py.
    if level is Degradation.FAX:
        angle = rng.uniform(-1.5, 1.5)
        noise = 0.022
        contrast = 0.65
        scale_x, scale_y = 0.68, 0.34
        blur = 0.90
    else:  # BAD_FAX
        angle = rng.uniform(-3.5, 3.5)
        noise = 0.032
        contrast = 0.52
        scale_x, scale_y = 0.58, 0.33
        blur = 1.00

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

    # 3) Resolution loss, optical blur, then noise (all pixel-local)
    #
    # Deliberately NOT binarized. A threshold pass gives the classic 1-bit "fax look",
    # but measurement showed it *raises* recall: hard thresholding restores crisp glyph
    # edges from a blurred scan, so it repairs the very damage the slice exists to model.
    # Faxes are binary in transit; what reaches an OCR pipeline is a re-scanned, softened
    # image, and that is what these slices reproduce.
    out = _resolution_loss(out, scale_x, scale_y)
    if blur:
        out = out.filter(ImageFilter.GaussianBlur(blur))
    out = _add_noise(out, rng, noise)

    new_labels = labels.model_copy(update={"fields": new_fields})
    return out, new_labels
