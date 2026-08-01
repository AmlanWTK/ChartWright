# chartwright-ocr (CP12)

Tier-0 OCR with the **grounding contract enforced** (ADR-0003): a deterministic OCR
engine produces per-token text + bounding boxes + confidence, and the grounding module
either *locates* a value's physical evidence or **refuses** — coordinates are never
invented.

## Why an OCR engine and not the VLM (design note, extends ADR-0008)

Grounding needs pixel locations. Small local VLMs read text but cannot reliably report
*where* it is; production layout-VLMs can, but need GPUs we've deferred. So local Tier-0
splits the job: **RapidOCR** (pip-installable ONNX PaddleOCR, CPU, real boxes) answers
*where/what characters*, and the Ollama VLM (CP14/CP15) answers *what it means*. The
`OcrEngine` protocol is the swap seam for production layout VLMs.

## API

```python
from chartwright_ocr import RapidOcrEngine, locate_value, verify_at

page = RapidOcrEngine().recognize(png_bytes)  # tokens in reading order, with boxes
match = locate_value(page, "A1234567")  # -> GroundingMatch(bbox, score) | None
ok = verify_at(page, "A1234567", claimed_bbox)  # audit a third-party location claim
```

- `locate_value` — fuzzy (OCR-noise-tolerant), spans up to 4 adjacent tokens, returns
  **None when the value isn't on the page** (the anti-hallucination property).
- `verify_at` — confirms a *claimed* location actually contains the value; this is what
  audits VLM extractor output in CP15.

## Evaluation (CP12 gate)

```bash
uv run python scripts/eval_ocr.py --count 10
```

Measures field recall, verify-at-gold rate, and grounding quality per degradation slice
(clean / fax / bad_fax) against pixel-accurate synthetic gold labels.

**Gates (clean slice):** recall ≥ 90% · coverage ≥ 0.95 · bloat ≤ 2.5. The script exits
non-zero on failure, so it can gate CI directly.

**Measured baseline** (10 docs/slice, RapidOCR on CPU):

| slice | recall | coverage | IoU | bloat |
|---------|-------:|---------:|-----:|------:|
| clean | 100.0% | 1.00 | 0.69 | 1.46 |
| fax | 99.2% | 1.00 | 0.56 | 1.83 |
| bad_fax | 79.2% | 0.98 | 0.62 | 1.64 |

That clean→bad_fax gap is exactly why the escalation cascade (CP17) exists, and these
numbers are its baseline.

### Why coverage, not IoU

The generator records a **tight ink box** (`draw.textbbox`); a detector returns a
**text-line box** padded to the font's ascender/descender. So even with pixel-perfect
localization the two disagree by a fixed offset — measured here as IoU ≈ 0.69 while
horizontal edges agree within ~3px. Raw IoU therefore understates grounding quality and
is reported for continuity only. **Coverage** (is the gold ink inside the box we
returned?) is what actually answers "did we point at the right thing", and **bloat**
(located area ÷ gold area) guards the opposite failure — a box swollen to half the page
would score perfect coverage while being useless in a review console.
