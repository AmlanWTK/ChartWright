"""Render a synthetic prior-authorization form and record pixel-accurate ground truth.

The key idea: the renderer measures and records the bounding box of every value *as it
draws it*, so labels are exact by construction — no annotation step, no label noise.
Output labels conform to ``chartwright_schemas.ExtractionResult``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from chartwright_schemas import (
    BoundingBox,
    DocType,
    ExtractionResult,
    GroundedField,
    Provenance,
)
from PIL import Image, ImageDraw, ImageFont

from chartwright_synthdata.values import SyntheticValues, make_values

PAGE_W, PAGE_H = 1700, 2200  # ~200 DPI letter portrait
MARGIN = 90
LABEL_GAP = 12


def _font(size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
    """Best-effort font loading: prefer a common TrueType, fall back to PIL default.

    Determinism of *layout* is preserved either way because positions are computed from
    measured text sizes with the same font object throughout a run.
    """
    for name in ("arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


@dataclass
class GeneratedDocument:
    """A rendered synthetic document plus its ground-truth labels."""

    image: Image.Image
    labels: ExtractionResult
    values: SyntheticValues


# (schema field key, printed label, attribute on SyntheticValues)
_FORM_ROWS: list[tuple[str, str, str]] = [
    ("member_name", "Member Name", "member_name"),
    ("member_id", "Member ID", "member_id"),
    ("member_dob", "Date of Birth", "member_dob"),
    ("payer_name", "Insurance / Payer", "payer_name"),
    ("plan_id", "Plan / Group Number", "plan_id"),
    ("ordering_provider_name", "Ordering Provider", "ordering_provider_name"),
    ("ordering_provider_npi", "Provider NPI", "ordering_provider_npi"),
    ("servicing_facility", "Servicing Facility", "servicing_facility"),
    ("diagnosis_code", "Diagnosis Code (ICD-10)", "diagnosis_code"),
    ("procedure_code", "Procedure Code (CPT)", "procedure_code"),
    ("date_of_service", "Requested Date of Service", "date_of_service"),
    ("urgency", "Urgency", "urgency"),
    ("contact_phone", "Contact Phone", "contact_phone"),
]


def generate_prior_auth(seed: int, document_id: str) -> GeneratedDocument:
    """Render one synthetic PA request form deterministically from ``seed``."""
    rng = random.Random(seed)  # noqa: S311 - non-cryptographic use is intentional
    values = make_values(rng)

    img = Image.new("L", (PAGE_W, PAGE_H), color=255)
    draw = ImageDraw.Draw(img)
    font_title = _font(46)
    font_label = _font(30)
    font_value = _font(34)

    # Header
    title = "PRIOR AUTHORIZATION REQUEST"
    draw.text((MARGIN, MARGIN), title, font=font_title, fill=0)
    draw.text(
        (MARGIN, MARGIN + 60),
        f"{values.payer_name} — Utilization Management",
        font=font_label,
        fill=60,
    )
    draw.line([(MARGIN, MARGIN + 110), (PAGE_W - MARGIN, MARGIN + 110)], fill=0, width=3)

    fields: list[GroundedField] = []
    y = MARGIN + 160
    label_col_x = MARGIN
    value_col_x = MARGIN + 560

    for key, printed_label, attr in _FORM_ROWS:
        value_text = getattr(values, attr)
        draw.text((label_col_x, y), f"{printed_label}:", font=font_label, fill=50)
        draw.text((value_col_x, y), value_text, font=font_value, fill=0)

        # Measure the exact ink box of the value text -> the ground-truth bbox.
        left, top, right, bottom = draw.textbbox((value_col_x, y), value_text, font=font_value)
        fields.append(
            GroundedField(
                key=key,
                value_raw=value_text,
                confidence=1.0,  # ground truth is certain by construction
                provenance=Provenance(
                    page=1,
                    bbox=BoundingBox(
                        x=float(left),
                        y=float(top),
                        w=float(max(right - left, 1)),
                        h=float(max(bottom - top, 1)),
                    ),
                    source_span=f"{printed_label}: {value_text}",
                ),
            )
        )
        y += 96

    # Justification block (free text; not a labeled schema field row in v1)
    draw.text((label_col_x, y + 20), "Clinical Justification:", font=font_label, fill=50)
    draw.rectangle([(label_col_x, y + 64), (PAGE_W - MARGIN, y + 260)], outline=0, width=2)
    draw.text(
        (label_col_x + 16, y + 80),
        f"Patient with {values.diagnosis_code}; requesting {values.procedure_description}",
        font=font_label,
        fill=0,
    )

    # Footer signature line
    draw.line([(MARGIN, PAGE_H - 200), (MARGIN + 600, PAGE_H - 200)], fill=0, width=2)
    draw.text((MARGIN, PAGE_H - 190), "Provider Signature", font=font_label, fill=50)

    labels = ExtractionResult(
        document_id=document_id,
        doc_type=DocType.PRIOR_AUTH_REQUEST,
        doc_type_confidence=1.0,
        page_count=1,
        fields=fields,
        overall_confidence=1.0,
    )
    return GeneratedDocument(image=img, labels=labels, values=values)
