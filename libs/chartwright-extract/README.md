# chartwright-extract (CP15)

Structured extraction: pulls the fields declared in a document type's `DocSchema` off the
page, each carrying mandatory provenance (page + bbox + source span) per ADR-0003.

**It calls no model.** These are forms: `FieldSpec.label` holds the label as printed, and
the value sits beside it or beneath it. Finding the label in CP12's OCR tokens and reading
the run of tokens next to it extracts the field exactly, with pixel-accurate grounding,
deterministically, for free.

## Why there is no model here

CP15's Phase 0 spike measured three reading paths on identical documents *before* anything
was built — 6 synthetic PA forms, 4 fields, 48 model calls:

| Arm | Grounded | Correct |
|-----|----------|---------|
| VLM, question prompt (*"What is the {label}?"*) | **0/24** | **0/24** |
| VLM, bare label (*"{label}:"*) | **0/24** | **0/24** |
| **OCR label anchor — no model** | **24/24** | **23/24** |

Both VLM arms produced zero groundable output; what they produced was
`urn:ietf:params:member:...` and `ids/23/0`. moondream describes images, it does not answer
questions about them, and per-field extraction is inherently question-form.

This is not a retreat from the AI core. ADR-0002's cascade routes each page to the
cheapest thing that can handle it, and free-and-deterministic is cheaper than Tier-0 — the
anchor is the cascade's bottom rung. VLM escalation for fields the anchor cannot find
belongs to CP17, whose job is the escalation cascade. See ADR-0011.

## API

```python
from chartwright_extract import extract_document, anchor_field

result = extract_document(pages, DocType.PRIOR_AUTH_REQUEST, document_id="d1")
# -> ExtractionResult(fields=[GroundedField(key="member_id", value_raw="A21743360", ...)])

match = anchor_field(page, "Member ID")
# -> AnchorMatch(value="A21743360", bbox=..., label_score=1.0, token_confidence=0.95)
```

A field whose label cannot be found, or which has no value tokens beside it, is **absent**
from the result — never fabricated (ADR-0003). How often that happens is CP15's most
load-bearing metric: it is precisely the work CP17's escalation will have to pick up.

`extract_document` raises only on empty input; a document with no OCR pages is an upstream
bug, not an extraction failure.

## What grounding does and does not prove

> **Grounding proves that text is at that location. It does not prove the text was read
> correctly.**

The Phase 0 spike's single miss was `Drew Iyer` read as `Drew lyer` — capital I as
lowercase l. The anchor found the correct region; RapidOCR misrecognized the glyph. The
result was grounded, plausible, and wrong.

**A grounded field is not a verified field.** ADR-0003 defends against fabrication, not
against misrecognition. CP16 (validation, code systems) and CP17 (calibration) are the
defenses against OCR error; provenance is not one.

## Confidence

Derived as `label_score × token_confidence` — how well the printed label matched, times
the engine's own confidence in the value tokens. Both factors matter: a crisp label over
mush is as suspect as mush beside a confident value.

**UNCALIBRATED.** Do not route on it before CP17.

## Known limitations (v1)

- **Brittle in exactly the way synthetic data hides.** Depends on reading the printed label
  and on a regular label:value geometry. Skew, wrapped values, multi-column layouts and
  checkbox fields all break it, and none of them appear in the clean slice.
- `MIN_LABEL_SCORE = 0.75` is a measured threshold, not a universal constant. It cleanly
  separates the real schema's confusable pairs (`Member ID` vs `Member Name` both score
  0.70 against each other, exact labels score 1.00), but a denser schema would need
  re-measuring.
- **Tables are out of scope** — `TableSpec` is declared but not extracted (CP16 or later).
- `value_normalized` and `code_system` are always `None` — CP16's job.
- One value per field per document; the strongest label match across pages wins.
