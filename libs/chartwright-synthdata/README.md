# chartwright-synthdata

Generates **synthetic** clinical documents (v1: prior-authorization request forms) as page images, together with **pixel-accurate ground-truth labels** that conform to the grounding contract in `chartwright-schemas`.

This is how we develop and evaluate without PHI:

- Every value is fabricated (seeded, deterministic). Names/IDs/codes come from small synthetic pools — **no real people, no real data**.
- The renderer records the bounding box of every field as it draws it, so labels are exact by construction — this seeds the gold sets for the eval harness (CP26) and the clean-tier accuracy targets for Tier-0 OCR (CP12).
- **Degradation levels** simulate the real-world fax distribution: `clean` (300 DPI scan), `fax` (noise + slight skew + threshold), `bad_fax` (heavy noise, skew, low contrast) — so we can measure accuracy per difficulty slice from day one.

## Usage

```bash
# generate 20 documents at mixed degradation into ./data/synth
uv run synthdata --count 20 --out data/synth --seed 42

# only bad faxes (the hard slice)
uv run synthdata --count 10 --out data/synth-hard --degradation bad_fax --seed 7
```

Output per document:

```
data/synth/
  pa_000001.png            # the page image
  pa_000001.labels.json    # ExtractionResult-conformant ground truth (bboxes, values)
  manifest.json            # run metadata: seed, counts, degradation mix
```

## Guarantees

- **Deterministic:** same seed → identical documents and labels.
- **Schema-conformant:** labels validate against `chartwright_schemas.ExtractionResult`.
- **Degradation never moves ink:** noise/contrast/threshold are pixel-local, and skew is
  applied by rotating image *and* bboxes together, so labels stay pixel-accurate.

## Limitations (deliberate, documented)

- v1 renders one form family for `prior_auth_request`; more layouts, handwriting simulation,
  checkboxes, and multi-page packets are added when CP13/CP15 need them.
- Synthetic ≠ real distribution. It anchors the *clean* and *structural* slices of the gold
  set; real de-identified documents (CP27) anchor realism.
