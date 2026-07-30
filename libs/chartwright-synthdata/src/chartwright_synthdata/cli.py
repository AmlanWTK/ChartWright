"""CLI: generate a batch of synthetic documents + ground-truth labels + manifest.

Usage:
    uv run synthdata --count 20 --out data/synth --seed 42
    uv run synthdata --count 10 --out data/hard --degradation bad_fax --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from chartwright_synthdata.degrade import Degradation, degrade
from chartwright_synthdata.generator import generate_prior_auth

# Default mix approximating a realistic fax-heavy intake distribution.
_DEFAULT_MIX: list[tuple[Degradation, float]] = [
    (Degradation.CLEAN, 0.4),
    (Degradation.FAX, 0.4),
    (Degradation.BAD_FAX, 0.2),
]


def _pick_level(rng: random.Random) -> Degradation:
    r = rng.random()
    cum = 0.0
    for level, p in _DEFAULT_MIX:
        cum += p
        if r <= cum:
            return level
    return Degradation.CLEAN


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic PA documents + labels.")
    parser.add_argument("--count", type=int, default=10, help="Number of documents.")
    parser.add_argument("--out", type=Path, required=True, help="Output directory.")
    parser.add_argument("--seed", type=int, default=42, help="Master seed (deterministic runs).")
    parser.add_argument(
        "--degradation",
        choices=[d.value for d in Degradation] + ["mixed"],
        default="mixed",
        help="Degradation level, or 'mixed' for a realistic distribution.",
    )
    args = parser.parse_args()

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)  # noqa: S311 - non-cryptographic use is intentional

    manifest: dict[str, object] = {
        "seed": args.seed,
        "count": args.count,
        "degradation": args.degradation,
        "documents": [],
    }
    docs_meta: list[dict[str, str]] = []

    for i in range(1, args.count + 1):
        doc_seed = rng.randrange(2**31)
        doc_id = f"pa_{i:06d}"
        generated = generate_prior_auth(seed=doc_seed, document_id=doc_id)

        level = Degradation(args.degradation) if args.degradation != "mixed" else _pick_level(rng)
        image, labels = degrade(generated.image, generated.labels, level, seed=doc_seed)

        image_path = out_dir / f"{doc_id}.png"
        labels_path = out_dir / f"{doc_id}.labels.json"
        image.save(image_path)
        labels_path.write_text(labels.model_dump_json(indent=2), encoding="utf-8")
        docs_meta.append({"id": doc_id, "degradation": level.value, "seed": str(doc_seed)})

    manifest["documents"] = docs_meta
    (out_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"Generated {args.count} documents in {out_dir} (seed={args.seed}).")


if __name__ == "__main__":
    main()
