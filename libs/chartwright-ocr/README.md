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

Measures field recall, verify-at-gold rate, and grounding IoU per degradation slice
(clean / fax / bad_fax) against pixel-accurate synthetic gold labels. Gate: **clean-slice
recall ≥ 90%**. Expect visible degradation on fax/bad_fax — that gap is exactly why the
escalation cascade (CP17) exists, and these numbers become its baseline.
