"""Packet splitting: partition a multi-page upload into logical documents.

Structural signals only — no classification (CP14) or OCR text (Tier-0 runs after
CLASSIFIED in ``STATUS_ORDER``) is available yet at the point this runs. The splitter
is a protocol, matching the ``OcrEngine`` pattern from CP12, so a classifier-informed
splitter can replace ``HeuristicSplitter`` later without changing callers.

The v1 heuristic is expected to be imperfect on real-world packets — it is tuned and
measured against synthetic multi-document packets (see ``scripts/eval_preprocess.py``),
not assumed correct. State that plainly rather than hiding it.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import pairwise
from typing import Protocol

import numpy as np
from PIL import Image

# A page is "blank" (a fax separator sheet) below this fraction of dark pixels.
_BLANK_INK_THRESHOLD = 0.01

# Adjacent non-blank pages are treated as a document boundary when the weighted
# structural distance between their PageFeatures exceeds this. Tuned empirically
# against synthetic packets (scripts/eval_preprocess.py): true cross-document distances
# measured ~0.19, same-document noisy-duplicate distances measured ~0.0 (20/20 pairs),
# so 0.15 sits centered in a wide (0.08-0.18, all-correct) working range with margin on
# both sides rather than pinned to the observed gap's edge.
_BOUNDARY_DISTANCE_THRESHOLD = 0.15


@dataclass(frozen=True)
class PageFeatures:
    """Cheap structural summary of one page, used for boundary scoring only.

    Deliberately not semantic (no OCR, no classification) — only pixel statistics
    available immediately after normalization.
    """

    ink_density: float  # fraction of dark pixels, page-wide
    top_band_density: float  # ink density in the top 15% of the page (header/title proxy)
    ink_bbox: tuple[float, float, float, float]  # (x0,y0,x1,y1), normalized to [0,1]

    @property
    def is_blank(self) -> bool:
        return self.ink_density < _BLANK_INK_THRESHOLD


@dataclass(frozen=True)
class Packet:
    """One logical document within a multi-page upload: a contiguous page range.

    ``page_indices`` are 0-based indices into the input page sequence *after* blank
    separator pages have been removed from consideration as content (they still count
    for locating boundaries, but never belong to a packet themselves).
    """

    page_indices: tuple[int, ...]
    boundary_score: float  # distance that triggered the split before this packet (0 for the first)


class PacketSplitter(Protocol):
    def split(self, pages: list[Image.Image]) -> list[Packet]: ...


def page_features(img: Image.Image, *, ink_threshold: float = 200.0) -> PageFeatures:
    """Compute cheap structural features for one page."""
    if img.mode != "L":
        img = img.convert("L")
    arr = np.asarray(img, dtype=np.float64)
    h, w = arr.shape
    ink = arr < ink_threshold
    total = ink.sum()
    ink_density = float(total) / (h * w)

    top_band = ink[: max(int(h * 0.15), 1), :]
    top_band_density = float(top_band.sum()) / top_band.size if top_band.size else 0.0

    if total == 0:
        bbox = (0.0, 0.0, 0.0, 0.0)
    else:
        ys, xs = np.nonzero(ink)
        bbox = (
            float(xs.min()) / w,
            float(ys.min()) / h,
            float(xs.max()) / w,
            float(ys.max()) / h,
        )

    return PageFeatures(ink_density=ink_density, top_band_density=top_band_density, ink_bbox=bbox)


def _feature_distance(a: PageFeatures, b: PageFeatures) -> float:
    """Weighted structural distance between two pages' features, roughly in [0, ~2].

    Ink density and top-band density each carry weight 1.0 (they're the strongest
    signal that two adjacent pages come from visually distinct sources); bbox distance
    carries weight 0.5 since layout can legitimately vary page-to-page within one
    multi-page document (e.g. a signature page has a much smaller ink bbox than a form
    page) and shouldn't alone trigger a split.
    """
    d_ink = abs(a.ink_density - b.ink_density)
    d_top = abs(a.top_band_density - b.top_band_density)
    ax0, ay0, ax1, ay1 = a.ink_bbox
    bx0, by0, bx1, by1 = b.ink_bbox
    d_bbox = (abs(ax0 - bx0) + abs(ay0 - by0) + abs(ax1 - bx1) + abs(ay1 - by1)) / 4.0
    return d_ink + d_top + 0.5 * d_bbox


class HeuristicSplitter:
    """v1 packet splitter: blank-page separators + structural discontinuity.

    Two independent boundary signals, either sufficient on its own:
    1. A blank (near-empty) page is a fax separator sheet; it is dropped from the
       output and a boundary is placed on either side of it.
    2. Between two adjacent non-blank pages, a large jump in ink density / header
       presence / content bounding box is treated as a new document starting.
    """

    def __init__(
        self,
        *,
        blank_threshold: float = _BLANK_INK_THRESHOLD,
        boundary_threshold: float = _BOUNDARY_DISTANCE_THRESHOLD,
    ) -> None:
        self._blank_threshold = blank_threshold
        self._boundary_threshold = boundary_threshold

    def split(self, pages: list[Image.Image]) -> list[Packet]:
        if not pages:
            return []

        features = [page_features(p) for p in pages]
        content_indices = [
            i for i, f in enumerate(features) if f.ink_density >= self._blank_threshold
        ]
        if not content_indices:
            return []

        packets: list[Packet] = []
        current: list[int] = [content_indices[0]]
        for prev_i, cur_i in pairwise(content_indices):
            # A blank run (or any gap) between the two content pages is itself a
            # boundary, regardless of feature distance.
            gapped = cur_i - prev_i > 1
            dist = _feature_distance(features[prev_i], features[cur_i])
            if gapped or dist > self._boundary_threshold:
                packets.append(Packet(page_indices=tuple(current), boundary_score=0.0))
                current = [cur_i]
            else:
                current.append(cur_i)
        packets.append(Packet(page_indices=tuple(current), boundary_score=0.0))
        return packets
