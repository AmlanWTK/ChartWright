"""Page normalization + packet splitting (CP13): pixel-only, deterministic, no model calls.

Prepares a raw upload for CP14 (classification) and Tier-0 OCR (CP12) by (1) correcting
page-level geometry — orientation, skew, contrast — and (2) partitioning a multi-page
upload into logical documents ("packets") using structural signals only, since neither
classification nor OCR text exists yet at this point in the pipeline
(``STATUS_ORDER``: RECEIVED -> NORMALIZED -> CLASSIFIED -> OCR_DONE -> ...).
"""

from __future__ import annotations

from chartwright_preprocess.io import file_type_from_extension, load_pages
from chartwright_preprocess.normalize import (
    NormalizedPage,
    detect_orientation,
    detect_skew,
    normalize_page,
)
from chartwright_preprocess.splitting import (
    HeuristicSplitter,
    Packet,
    PacketSplitter,
    PageFeatures,
    page_features,
)

__all__ = [
    "HeuristicSplitter",
    "NormalizedPage",
    "Packet",
    "PacketSplitter",
    "PageFeatures",
    "detect_orientation",
    "detect_skew",
    "file_type_from_extension",
    "load_pages",
    "normalize_page",
    "page_features",
]
