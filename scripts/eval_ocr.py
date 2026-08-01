"""CP12 acceptance eval: OCR field recall + grounding IoU per degradation slice.

Generates synthetic PA documents (pixel-accurate gold labels), runs the Tier-0 engine,
and measures, per slice (clean/fax/bad_fax):

- field recall: gold value locatable in the OCR output (locate_value >= threshold)
- grounding IoU: overlap between the located bbox and the gold bbox
- verifier accuracy: verify_at() confirms gold values at gold locations

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


def iou(a: BoundingBox, b: BoundingBox) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    inter = (x1 - x0) * (y1 - y0)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union


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
                    s.iou_count += 1
                elif len(s.misses) < 5:
                    s.misses.append(f"{level.value}:{f.key}={f.value_raw!r}")
                if verify_at(page, f.value_raw, f.provenance.bbox):
                    s.verified_at_gold += 1

    print(f"\nTier-0 OCR eval — {args.count} docs/slice, engine={engine.name}\n")
    print(f"{'slice':<10} {'recall':>8} {'verify@gold':>12} {'mean IoU':>9} {'s/page':>7}")
    for name, s in stats.items():
        print(
            f"{name:<10} {s.recall:>7.1%} {s.verify_rate:>11.1%} "
            f"{s.mean_iou:>9.2f} {s.latency_s / max(s.pages, 1):>7.2f}"
        )
    if any(s.misses for s in stats.values()):
        print("\nSample misses (max 5/slice):")
        for s in stats.values():
            for m in s.misses:
                print(f"  - {m}")

    clean = stats[Degradation.CLEAN.value]
    print(
        f"\nCP12 gate (clean slice): recall {clean.recall:.1%} "
        f"{'PASS' if clean.recall >= 0.90 else 'FAIL'} (target >= 90%)"
    )


if __name__ == "__main__":
    main()
