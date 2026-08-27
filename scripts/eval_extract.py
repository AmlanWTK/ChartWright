"""CP15 acceptance eval: grounded field extraction, per degradation slice.

Mirrors eval_ocr.py / eval_preprocess.py / eval_classify.py in shape and in honesty
discipline: report what was measured, never a target restated as a result.

CP14's gate conflated "does the mechanism work" with "is the model any good" into one
number, and the checkpoint nearly closed on a misreading of it. This eval keeps the two
apart, because they fail for different reasons and deserve different verdicts:

  MECHANISM GATES (hard failures -- these test our code)
    * self-verification: every emitted field must verify_at its own claimed bbox. A field
      whose value is not at the location it points to is a grounding bug, full stop.
    * schema conformance: no emitted key outside the DocSchema.
    * determinism: the same pages must produce byte-identical results.

  CAPABILITY GATES (clean slice only; degraded slices are measured, not judged)
    * exact-match accuracy, per field and per slice.
    * critical-field accuracy, reported against the 95% NFR as a GAP, not pass/fail --
      per ADR-0008, accuracy targets bind at CP17/CP26 with whatever engines exist then.
    * missed-field rate: with no model fallback (ADR-0011), a field the anchor cannot
      find is simply absent. How often that happens is the number that sizes CP17's
      escalation cascade, so it is a headline metric here, not a footnote.

On "exact" vs "fuzzy": the two columns differ by exactly the OCR misrecognition rate.
Phase 0's one miss was `Drew Iyer` read as `Drew lyer` -- correctly located, grounded,
plausible, and wrong. Exact match counts that as a failure, because it is one; the fuzzy
column shows how much of the loss is the OCR engine rather than the anchor, which is the
difference between "fix the extractor" and "fix Tier-0".

Usage:  uv run python scripts/eval_extract.py --count 10
"""

from __future__ import annotations

import argparse
import io
from collections import defaultdict
from dataclasses import dataclass, field

from chartwright_extract import extract_document
from chartwright_ocr import RapidOcrEngine, normalize, similarity, verify_at
from chartwright_schemas import BoundingBox
from chartwright_schemas.documents import SCHEMA_REGISTRY
from chartwright_schemas.taxonomy import DocType
from chartwright_synthdata import Degradation, degrade, generate_prior_auth

_SCHEMA = SCHEMA_REGISTRY[DocType.PRIOR_AUTH_REQUEST]
_CRITICAL = _SCHEMA.critical_keys()

# A value is "fuzzily" right when it differs from gold only by OCR noise.
_FUZZY_THRESHOLD = 0.90


@dataclass
class FieldStats:
    gold: int = 0
    predicted: int = 0
    exact: int = 0
    fuzzy: int = 0
    iou_sum: float = 0.0
    iou_count: int = 0

    @property
    def accuracy(self) -> float:
        return self.exact / self.gold if self.gold else 0.0

    @property
    def fuzzy_accuracy(self) -> float:
        return self.fuzzy / self.gold if self.gold else 0.0

    @property
    def missed_rate(self) -> float:
        return (self.gold - self.predicted) / self.gold if self.gold else 0.0

    @property
    def mean_iou(self) -> float:
        return self.iou_sum / self.iou_count if self.iou_count else 0.0


@dataclass
class SliceStats:
    fields: dict[str, FieldStats] = field(default_factory=lambda: defaultdict(FieldStats))
    unverified: int = 0  # emitted fields that fail verify_at against their OWN provenance
    off_schema: int = 0  # emitted keys not in the DocSchema
    extra_vs_gold: int = 0  # emitted keys the gold set does not cover
    emitted: int = 0
    docs: int = 0
    misses: list[str] = field(default_factory=list)

    def totals(self) -> FieldStats:
        out = FieldStats()
        for s in self.fields.values():
            out.gold += s.gold
            out.predicted += s.predicted
            out.exact += s.exact
            out.fuzzy += s.fuzzy
            out.iou_sum += s.iou_sum
            out.iou_count += s.iou_count
        return out

    def critical(self) -> FieldStats:
        out = FieldStats()
        for key, s in self.fields.items():
            if key in _CRITICAL:
                out.gold += s.gold
                out.exact += s.exact
                out.predicted += s.predicted
        return out


def _intersection(a: BoundingBox, b: BoundingBox) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    if x1 <= x0 or y1 <= y0:
        return 0.0
    return (x1 - x0) * (y1 - y0)


def verdict(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def iou(a: BoundingBox, b: BoundingBox) -> float:
    inter = _intersection(a, b)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate CP15 grounded field extraction.")
    parser.add_argument("--count", type=int, default=10, help="Documents per slice.")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    engine = RapidOcrEngine()
    stats: dict[str, SliceStats] = defaultdict(SliceStats)
    determinism_ok = True

    for level in (Degradation.CLEAN, Degradation.FAX, Degradation.BAD_FAX):
        for i in range(args.count):
            doc_seed = args.seed * 1000 + i
            generated = generate_prior_auth(seed=doc_seed, document_id=f"eval_{doc_seed}")
            image, labels = degrade(generated.image, generated.labels, level, seed=doc_seed)

            buf = io.BytesIO()
            image.save(buf, format="PNG")
            page = engine.recognize(buf.getvalue())
            result = extract_document([page], DocType.PRIOR_AUTH_REQUEST, f"eval_{doc_seed}")

            # Determinism is a property of a model-free extractor; assert it, do not assume.
            if i == 0 and level is Degradation.CLEAN:
                again = extract_document([page], DocType.PRIOR_AUTH_REQUEST, f"eval_{doc_seed}")
                determinism_ok = [(f.key, f.value_raw) for f in result.fields] == [
                    (f.key, f.value_raw) for f in again.fields
                ]

            s = stats[level.value]
            s.docs += 1
            s.emitted += len(result.fields)
            gold = {f.key: f for f in labels.fields}
            predicted = {f.key: f for f in result.fields}

            for key, pred in predicted.items():
                if key not in _SCHEMA.field_keys():
                    s.off_schema += 1
                if not verify_at(page, pred.value_raw, pred.provenance.bbox):
                    s.unverified += 1
                if key not in gold:
                    s.extra_vs_gold += 1

            for key, truth in gold.items():
                fs = s.fields[key]
                fs.gold += 1
                pred = predicted.get(key)
                if pred is None:
                    if len(s.misses) < 8:
                        s.misses.append(f"{level.value}:{key} MISSED (want {truth.value_raw!r})")
                    continue
                fs.predicted += 1
                score = similarity(pred.value_raw, truth.value_raw)
                if normalize(pred.value_raw) == normalize(truth.value_raw):
                    fs.exact += 1
                    fs.fuzzy += 1
                elif score >= _FUZZY_THRESHOLD:
                    fs.fuzzy += 1
                    if len(s.misses) < 8:
                        s.misses.append(
                            f"{level.value}:{key} OCR-NOISE want={truth.value_raw!r} "
                            f"got={pred.value_raw!r}"
                        )
                elif len(s.misses) < 8:
                    s.misses.append(
                        f"{level.value}:{key} WRONG want={truth.value_raw!r} got={pred.value_raw!r}"
                    )
                fs.iou_sum += iou(pred.provenance.bbox, truth.provenance.bbox)
                fs.iou_count += 1

    print(f"\nCP15 eval — {args.count} docs/slice, engine={engine.name}\n")
    header = f"{'slice':<10}{'exact':>9}{'fuzzy':>9}{'missed':>9}{'IoU':>7}{'critical':>10}"
    print(header)
    print("-" * len(header))
    for level in (Degradation.CLEAN, Degradation.FAX, Degradation.BAD_FAX):
        s = stats[level.value]
        t = s.totals()
        c = s.critical()
        print(
            f"{level.value:<10}{t.accuracy:>8.1%}{t.fuzzy_accuracy:>9.1%}"
            f"{t.missed_rate:>9.1%}{t.mean_iou:>7.2f}{c.accuracy:>10.1%}"
        )

    clean = stats[Degradation.CLEAN.value]
    print(f"\nPer-field accuracy (clean slice, {clean.docs} docs):")
    print(f"  {'field':<28}{'exact':>8}{'missed':>9}  critical")
    for key in (f.key for f in _SCHEMA.fields):
        fs = clean.fields.get(key)
        if fs is None or not fs.gold:
            print(f"  {key:<28}{'--':>8}{'--':>9}  {'yes' if key in _CRITICAL else ''}")
            continue
        print(
            f"  {key:<28}{fs.accuracy:>7.0%}{fs.missed_rate:>9.0%}"
            f"  {'yes' if key in _CRITICAL else ''}"
        )

    print("\nSample failures:")
    for line in clean.misses[:8]:
        print(f"  {line}")

    unverified = sum(s.unverified for s in stats.values())
    off_schema = sum(s.off_schema for s in stats.values())
    extra = sum(s.extra_vs_gold for s in stats.values())
    emitted = sum(s.emitted for s in stats.values())
    clean_exact = clean.totals().accuracy
    crit = clean.critical().accuracy

    print("\nMechanism gates (hard — these test our code, not the engine):")
    print(f"  self-verification failures  {unverified:>6} / {emitted}   {verdict(not unverified)}")
    print(f"  off-schema keys emitted     {off_schema:>6}          {verdict(not off_schema)}")
    print(
        f"  deterministic re-run        {'same' if determinism_ok else 'DIFFERS':>6}"
        f"          {verdict(determinism_ok)}"
    )

    print("\nCapability gates (clean slice binds; degraded slices measured, not judged):")
    print(
        f"  clean exact-match           {clean_exact:>6.1%}          "
        f"{verdict(clean_exact >= 0.90)}  (target >= 90%)"
    )
    print(
        f"  critical-field accuracy     {crit:>6.1%}          "
        f"gap vs 95% NFR: {0.95 - crit:+.1%}  (reported, not gated)"
    )
    print(
        f"  emitted keys not in gold    {extra:>6}          "
        "(gold coverage, not invention — see docstring)"
    )

    hard_pass = not unverified and not off_schema and determinism_ok
    passed = hard_pass and clean_exact >= 0.90
    print(f"\nCP15: {'PASS' if passed else 'FAIL'}\n")
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
