# chartwright-preprocess (CP13)

Page normalization + packet splitting: prepares a raw upload for CP14 (classification)
and Tier-0 OCR (CP12) by correcting page-level geometry and partitioning a multi-page
upload into logical documents. No model calls — deterministic, pixel-only, same as
CP12's Tier-0 OCR.

## Why this runs before classification

`services/pipeline`'s `STATUS_ORDER` is `RECEIVED -> NORMALIZED -> CLASSIFIED ->
OCR_DONE -> ...`. Neither classification nor OCR text exists at the `NORMALIZED` stage,
so both the orientation/skew correction and the packet splitter work from raw pixel
statistics only — no semantic signal is available yet.

## API

```python
from chartwright_preprocess import normalize_page, HeuristicSplitter

result = normalize_page(
    page_image
)  # -> NormalizedPage(image, rotation_deg, skew_angle_deg, contrast_factor)
packets = HeuristicSplitter().split(pages)  # -> list[Packet(page_indices=(...), ...)]
```

- `normalize_page` — corrects 0/90/180/270 orientation (row-projection-variance axis
  test + upper/lower ink-asymmetry tie-break) and fine skew (narrow-range projection
  search), then applies a fixed contrast boost. Every transform parameter is returned
  on `NormalizedPage`, never applied silently — the same discipline as
  `chartwright_synthdata.degrade`'s bbox-preserving transforms, in reverse.
- `HeuristicSplitter` — partitions pages into `Packet`s using two structural signals:
  blank (near-empty) fax-separator pages, and large jumps in ink density / header
  presence / content bounding box between adjacent non-blank pages. **v1 is a
  heuristic, not a classifier** — it is a `PacketSplitter` protocol implementation
  (matching CP12's `OcrEngine` pattern) so a classifier-informed splitter can replace
  it later without changing callers.

## Evaluation (CP13 gate)

```bash
uv run python scripts/eval_preprocess.py --count 20
```

Measures orientation-correction accuracy against synthetic 0/90/180/270-rotated pages,
and packet-boundary precision/recall against synthetic multi-document packets (with and
without blank separators — see `chartwright_synthdata.packets`). Gates: orientation
accuracy ≥ 95%, split precision and recall ≥ 85% in both conditions. The script exits
non-zero on failure.

**Measured baseline** (20 docs/packets per condition):

| metric | value |
|---|---:|
| orientation accuracy | 100.0% |
| split precision (blank separators) | 100.0% |
| split recall (blank separators) | 100.0% |
| split precision (no separators) | 100.0% |
| split recall (no separators) | 100.0% |

These are near-ceiling because the synthetic packets use clearly distinct page shapes
(dense form vs. sparse card vs. blank). Real-world packets will be harder — closely
related document types, inconsistent fax quality, and true multi-page single documents
are all expected to push these numbers down. The eval exists to catch regressions and
give CP14 an honest starting baseline, not to claim production-readiness.

## Known limitations (v1)

- The boundary-distance threshold (`0.15`) is tuned empirically against this repo's
  synthetic generator, not derived analytically. Re-run the eval after any change to
  `chartwright_synthdata.generator` or `packets`.
- A genuinely multi-page *single* document (e.g. a 2-page PA form) is only tested
  against noisy re-renders of the same template, not a real second page. False-positive
  risk there is plausible and untested beyond that proxy.
- No use of CP12's OCR or CP11's model gateway — intentional (see "Why this runs
  before classification" above), but means the splitter cannot use text content even
  where it would obviously help disambiguate.
