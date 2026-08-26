"""Document-level extraction: DocSchema + OCR pages -> a validated ExtractionResult.

Assembles the fields ``anchor_field`` can locate into the CP03 envelope. Everything the
anchor cannot find is simply absent -- never fabricated, never guessed (ADR-0003). The
missed-field rate that produces is CP15's most load-bearing metric: it is exactly the work
CP17's escalation cascade will have to pick up.
"""

from __future__ import annotations

from collections.abc import Sequence

from chartwright_ocr import PageOcr
from chartwright_schemas import ExtractionResult, GroundedField, Provenance
from chartwright_schemas.documents import SCHEMA_REGISTRY
from chartwright_schemas.taxonomy import DocType

from chartwright_extract.anchor import MIN_LABEL_SCORE, AnchorMatch, anchor_field


def _best_across_pages(
    pages: Sequence[PageOcr], label: str, min_label_score: float
) -> tuple[int, AnchorMatch] | None:
    """Best anchor for ``label`` over every page, as (1-based page number, match).

    A field appears once in a packet but we do not know which page, so all pages are
    searched and the strongest label match wins. Ties keep the earlier page, which matches
    how forms actually read.
    """
    best: tuple[int, AnchorMatch] | None = None
    for index, page in enumerate(pages, start=1):
        match = anchor_field(page, label, min_label_score=min_label_score)
        if match is None:
            continue
        if best is None or match.label_score > best[1].label_score:
            best = (index, match)
    return best


def extract_document(
    pages: Sequence[PageOcr],
    doc_type: DocType,
    document_id: str,
    *,
    doc_type_confidence: float = 1.0,
    min_label_score: float = MIN_LABEL_SCORE,
) -> ExtractionResult:
    """Extract every field the schema declares and the page actually supports.

    Deterministic: the same pages always produce the same result, which is what makes this
    testable without a model and reproducible in the eval. Raises only if ``pages`` is
    empty -- a document with no pages is an upstream bug, not an extraction failure, same
    discipline as the pipeline's missing-first-page guard.
    """
    if not pages:
        msg = f"document {document_id} has no OCR pages; cannot extract"
        raise ValueError(msg)

    schema = SCHEMA_REGISTRY.get(doc_type)
    fields: list[GroundedField] = []

    if schema is not None:
        for spec in schema.fields:
            found = _best_across_pages(pages, spec.label, min_label_score)
            if found is None:
                continue  # absent, not invented -- see module docstring
            page_number, match = found
            fields.append(
                GroundedField(
                    key=spec.key,
                    value_raw=match.value,
                    confidence=match.confidence,
                    provenance=Provenance(
                        page=page_number, bbox=match.bbox, source_span=match.value
                    ),
                    tier=0,
                )
            )

    overall = sum(f.confidence for f in fields) / len(fields) if fields else 0.0
    return ExtractionResult(
        document_id=document_id,
        doc_type=doc_type,
        doc_type_confidence=doc_type_confidence,
        page_count=len(pages),
        fields=fields,
        tables=[],  # tables are out of scope for CP15 (TableSpec.required is False)
        overall_confidence=max(0.0, min(1.0, overall)),
    )
