"""CP12 acceptance eval: OCR field recall + grounding IoU per degradation slice.

Generates synthetic PA documents (pixel-accurate gold labels), runs the Tier-0 engine,
and measures, per slice (clean/fax/bad_fax):

- field recall: gold value locatable in the OCR output (locate_value >= threshold)
- grounding coverage: fraction of the gold ink box contained in the located box
- grounding IoU + bloat: raw overlap, and how much larger the located box is
- verifier accuracy: verify_at() confirms gold values at gold locations

On coverage vs. IoU: the generator records a *tight ink* box (``draw.textbbox``), while
a detector returns a *text-line* box padded to the font's ascender/descender. The two
therefore never agree above ~0.7 IoU even when localization is pixel-perfect, so raw IoU
understates quality by a fixed definitional offset. Coverage ("is the gold ink inside the
box we returned?") is the metric that actually answers whether we pointed at the right
thing; bloat guards the other direction, since a box swollen to cover half the page would
score perfect coverage while being useless in a review console.

This is the seed of the CP26 eval harness: same metrics, same slices, versioned later.

Usage:  uv run python scripts/eval_ocr.py --count 10
"""

from __future__ import annotations

import argparse
import io
import time
from collections import defaultdict
from dataclasses import dataclass, field

from chartwright_ocr import RapidOcrEngine, locate_value, verify_at
from chartwright_schemas import BoundingBox
from chartwright_synthdata import Degradation, degrade, generate_prior_auth


@dataclass
class SliceStats:
    fields_total: int = 0
    fields_found: int = 0
    verified_at_gold: int = 0
    iou_sum: float = 0.0
    iou_count: int = 0
    coverage_sum: float = 0.0
    bloat_sum: float = 0.0
    latency_s: float = 0.0
    pages: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def recall(self) -> float:
        return self.fields_found / self.fields_total if self.fields_total else 0.0

    @property
    def verify_rate(self) -> float:
        return self.verified_at_gold / self.fields_total if self.fields_total else 0.0

    @property
    def mean_iou(self) -> float:
        return self.iou_sum / self.iou_count if self.iou_count else 0.0

    @property
    def mean_coverage(self) -> float:
        return self.coverage_sum / self.iou_count if self.iou_count else 0.0

    @property
    def mean_bloat(self) -> float:
        return self.bloat_sum / self.iou_count if self.iou_count else 0.0


def _intersection(a: BoundingBox, b: BoundingBox) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def iou(a: BoundingBox, b: BoundingBox) -> float:
    inter = _intersection(a, b)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union else 0.0


def coverage(located: BoundingBox, gold: BoundingBox) -> float:
    """Fraction of the gold ink box that falls inside the located box."""
    gold_area = gold.w * gold.h
    return _intersection(located, gold) / gold_area if gold_area else 0.0


def bloat(located: BoundingBox, gold: BoundingBox) -> float:
    """How many times larger the located box is than the gold ink box."""
    gold_area = gold.w * gold.h
    return (located.w * located.h) / gold_area if gold_area else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Tier-0 OCR against gold labels.")
    parser.add_argument("--count", type=int, default=10, help="Documents per slice.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    engine = RapidOcrEngine()
    stats: dict[str, SliceStats] = defaultdict(SliceStats)

    for level in (Degradation.CLEAN, Degradation.FAX, Degradation.BAD_FAX):
        for i in range(args.count):
            doc_seed = args.seed * 1000 + i
            generated = generate_prior_auth(seed=doc_seed, document_id=f"eval_{doc_seed}")
            image, labels = degrade(generated.image, generated.labels, level, seed=doc_seed)

            buf = io.BytesIO()
            image.save(buf, format="PNG")
            started = time.perf_counter()
            page = engine.recognize(buf.getvalue())
            elapsed = time.perf_counter() - started

            s = stats[level.value]
            s.pages += 1
            s.latency_s += elapsed
            for f in labels.fields:
                s.fields_total += 1
                match = locate_value(page, f.value_raw)
                if match is not None:
                    s.fields_found += 1
                    s.iou_sum += iou(match.bbox, f.provenance.bbox)
                    s.coverage_sum += coverage(match.bbox, f.provenance.bbox)
                    s.bloat_sum += bloat(match.bbox, f.provenance.bbox)
                    s.iou_count += 1
                elif len(s.misses) < 5:
                    s.misses.append(f"{level.value}:{f.key}={f.value_raw!r}")
                if verify_at(page, f.value_raw, f.provenance.bbox):
                    s.verified_at_gold += 1

    print(f"\nTier-0 OCR eval — {args.count} docs/slice, engine={engine.name}\n")
    header = (
        f"{'slice':<10} {'recall':>8} {'verify@gold':>12} "
        f"{'coverage':>9} {'IoU':>6} {'bloat':>6} {'s/page':>7}"
    )
    print(header)
    for name, s in stats.items():
        print(
            f"{name:<10} {s.recall:>7.1%} {s.verify_rate:>11.1%} "
            f"{s.mean_coverage:>9.2f} {s.mean_iou:>6.2f} {s.mean_bloat:>6.2f} "
            f"{s.latency_s / max(s.pages, 1):>7.2f}"
        )
    if any(s.misses for s in stats.values()):
        print("\nSample misses (max 5/slice):")
        for s in stats.values():
            for m in s.misses:
                print(f"  - {m}")

    clean = stats[Degradation.CLEAN.value]
    gates = [
        ("recall", clean.recall, 0.90, "min", f"{clean.recall:.1%}"),
        ("coverage", clean.mean_coverage, 0.95, "min", f"{clean.mean_coverage:.2f}"),
        ("bloat", clean.mean_bloat, 2.50, "max", f"{clean.mean_bloat:.2f}"),
    ]
    print("\nCP12 gate (clean slice):")
    failed = False
    for label, value, bound, kind, shown in gates:
        ok = value >= bound if kind == "min" else value <= bound
        failed = failed or not ok
        target = f"{'>=' if kind == 'min' else '<='} {bound:g}"
        print(f"  {label:<9} {shown:>7}  {'PASS' if ok else 'FAIL'}  (target {target})")
    print(f"\nCP12: {'FAIL' if failed else 'PASS'}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
