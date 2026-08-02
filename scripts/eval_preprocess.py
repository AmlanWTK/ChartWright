"""CP13 acceptance eval: orientation-correction accuracy + packet-boundary detection.

Two independent measurements against synthetic ground truth, mirroring
``scripts/eval_ocr.py``'s shape and honesty discipline (report what was actually
measured, not a target restated as a result):

- orientation: does ``detect_orientation`` recover 0/90/180/270 rotation correctly?
- packet splitting: does ``HeuristicSplitter`` recover document boundaries in
  synthetic multi-document packets, with and without blank fax-separator pages?

Usage:  uv run python scripts/eval_preprocess.py --count 20
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from chartwright_preprocess import HeuristicSplitter, detect_orientation
from chartwright_synthdata import generate_prior_auth
from chartwright_synthdata.packets import compose_packet_set

_ORIENTATIONS = (0, 90, 180, 270)


@dataclass
class OrientationStats:
    correct: int = 0
    total: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


@dataclass
class SplitStats:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0


def eval_orientation(count: int, seed: int) -> OrientationStats:
    stats = OrientationStats()
    for i in range(count):
        doc_seed = seed * 1000 + i
        g = generate_prior_auth(seed=doc_seed, document_id=f"orient_{doc_seed}")
        for true_angle in _ORIENTATIONS:
            rotated = g.image.rotate(true_angle, expand=True, fillcolor=255)
            detected = detect_orientation(rotated)
            stats.total += 1
            if detected == true_angle:
                stats.correct += 1
            elif len(stats.misses) < 5:
                stats.misses.append(f"seed={doc_seed} true={true_angle} detected={detected}")
    return stats


def eval_splitting(count: int, seed: int, *, use_blank_separators: bool) -> SplitStats:
    stats = SplitStats()
    splitter = HeuristicSplitter()
    for i in range(count):
        s = seed * 1000 + i
        for n_docs in (2, 3, 4):
            pk = compose_packet_set(
                seed=s, n_docs=n_docs, use_blank_separators=use_blank_separators
            )
            result = splitter.split(pk.pages)
            got = {p.page_indices for p in result}
            want = set(pk.boundaries)
            stats.tp += len(got & want)
            stats.fp += len(got - want)
            stats.fn += len(want - got)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CP13 preprocessing + packet splitting.")
    parser.add_argument("--count", type=int, default=20, help="Documents/packets per condition.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    orient = eval_orientation(args.count, args.seed)
    split_blank = eval_splitting(args.count, args.seed, use_blank_separators=True)
    split_no_blank = eval_splitting(args.count, args.seed, use_blank_separators=False)

    print(f"\nCP13 eval — {args.count} docs/packets per condition\n")
    print(f"Orientation correction: {orient.accuracy:.1%} ({orient.correct}/{orient.total})")
    if orient.misses:
        print("  misses:")
        for m in orient.misses:
            print(f"    - {m}")

    print("\nPacket splitting:")
    print(f"  {'condition':<20}{'precision':>11}{'recall':>9}")
    print(f"  {'blank separators':<20}{split_blank.precision:>10.1%}{split_blank.recall:>9.1%}")
    print(f"  {'no separators':<20}{split_no_blank.precision:>10.1%}{split_no_blank.recall:>9.1%}")

    gates = [
        ("orientation accuracy", orient.accuracy, 0.95),
        ("split precision (blank sep)", split_blank.precision, 0.85),
        ("split recall (blank sep)", split_blank.recall, 0.85),
        ("split precision (no sep)", split_no_blank.precision, 0.85),
        ("split recall (no sep)", split_no_blank.recall, 0.85),
    ]
    print("\nCP13 gates:")
    failed = False
    for label, value, bound in gates:
        ok = value >= bound
        failed = failed or not ok
        print(f"  {label:<30} {value:>7.1%}  {'PASS' if ok else 'FAIL'}  (target >= {bound:.0%})")
    print(f"\nCP13: {'FAIL' if failed else 'PASS'}")
    raise SystemExit(1 if failed else 0)


if __name__ == "__main__":
    main()
