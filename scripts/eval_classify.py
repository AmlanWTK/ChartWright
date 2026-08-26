"""CP14 acceptance eval: document classification accuracy against synthetic documents.

Mirrors ``scripts/eval_ocr.py``/``scripts/eval_preprocess.py``'s shape and honesty
discipline: report what was actually measured, not a target restated as a result. This
is the pipeline's first model-dependent gate — it calls the CP11 gateway's Tier-0 engine
(local Ollama) for real, so a low or zero score most often means Ollama isn't running
(``ollama pull moondream``) rather than a classifier bug; the script does not special-case
that, it just reports the honest number either way.

Usage:  uv run python scripts/eval_classify.py --count 20
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field

from chartwright_classify import classify_packet
from chartwright_gateway import build_default_gateway
from chartwright_schemas.taxonomy import DocType
from chartwright_synthdata import generate_prior_auth
from chartwright_synthdata.classify_docs import generate_insurance_card, generate_lab_report

# Every synthetic generator this eval knows about, and the DocType it should produce.
# Only three of the taxonomy's nine types have a generator today (CP14 scope) — this is
# a known, stated limitation, not silent partial coverage (see README's "Known limitations").
_GENERATORS = (
    ("prior_auth_request", generate_prior_auth, DocType.PRIOR_AUTH_REQUEST),
    ("insurance_card", generate_insurance_card, DocType.INSURANCE_CARD),
    ("lab_report", generate_lab_report, DocType.LAB_REPORT),
)


@dataclass
class TypeStats:
    correct: int = 0
    total: int = 0
    misses: list[str] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0


def eval_classification(count: int, seed: int) -> dict[str, TypeStats]:
    gateway = build_default_gateway()
    stats: dict[str, TypeStats] = {name: TypeStats() for name, _, _ in _GENERATORS}
    for i in range(count):
        doc_seed = seed * 1000 + i
        for name, generate, expected in _GENERATORS:
            g = generate(seed=doc_seed, document_id=f"{name}_{doc_seed}")
            result = classify_packet(g.image, gateway=gateway, tenant_id="eval")
            s = stats[name]
            s.total += 1
            if result.doc_type == expected:
                s.correct += 1
            elif len(s.misses) < 5:
                s.misses.append(
                    f"seed={doc_seed} expected={expected.value} got={result.doc_type.value} "
                    f"confidence={result.confidence:.2f}"
                )
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CP14 document classification.")
    parser.add_argument("--count", type=int, default=20, help="Documents per type.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    stats = eval_classification(args.count, args.seed)

    print(f"\nCP14 eval — {args.count} documents per type\n")
    total_correct = sum(s.correct for s in stats.values())
    total_docs = sum(s.total for s in stats.values())
    overall_accuracy = total_correct / total_docs if total_docs else 0.0

    print(f"{'type':<20}{'accuracy':>10}")
    for name, s in stats.items():
        print(f"{name:<20}{s.accuracy:>9.1%}")
        for m in s.misses:
            print(f"    miss: {m}")
    print(f"{'OVERALL':<20}{overall_accuracy:>9.1%}")

    gate_bound = 0.85
    passed = overall_accuracy >= gate_bound
    print("\nCP14 gate:")
    print(
        f"  classification accuracy   {overall_accuracy:>7.1%}  "
        f"{'PASS' if passed else 'FAIL'}  (target >= {gate_bound:.0%})"
    )
    print(f"\nCP14: {'PASS' if passed else 'FAIL'}")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
