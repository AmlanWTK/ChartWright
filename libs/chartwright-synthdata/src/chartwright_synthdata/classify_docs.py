"""Synthetic documents for CP14's classification eval, beyond CP03's prior-auth form.

CP14 needs at least a couple more visually distinct ``DocType``s to make classification
accuracy measurement meaningful — a single-type eval can't distinguish "classifies
correctly" from "always guesses the only type it's ever seen." Reuses ``values.py``'s
synthetic patient/payer data so all generated documents look like they belong to the
same (synthetic) world.

Not ground-truth-labeled for field extraction the way ``generate_prior_auth`` is — these
exist to be *classified*, not *extracted from* (that's CP15's structured-extraction
scope, not this one's). ``GeneratedDocument.labels`` is populated with an empty-fields
``ExtractionResult`` purely to satisfy the shared return shape.

Insurance-card note (CP14 verification): the first version of ``generate_insurance_card``
drew a small bordered block on a full letter-size portrait page, leaving ~85% of the
frame blank. Asked to describe it, the Tier-0 model said "a blank white page ... the page
is empty" — an accurate description of the image, which scored 0/4 on classification. A
member ID card is a landscape CR80 card that fills the frame, so that is what this now
renders. The lesson generalizes: a synthetic document that a human never looks at can
silently measure the generator instead of the model.
"""

from __future__ import annotations

import random

from chartwright_schemas import DocType, ExtractionResult
from PIL import Image, ImageDraw

from chartwright_synthdata.generator import MARGIN, PAGE_H, PAGE_W, GeneratedDocument, _font
from chartwright_synthdata.values import make_values

# A CR80 card (the ISO/IEC 7810 ID-1 size every insurance card uses) is 85.6mm x 54mm —
# a 1.586:1 landscape ratio. Rendered at a width matching the page renderer's ~200 DPI.
CARD_W, CARD_H = 1700, 1072

_LAB_TESTS: list[tuple[str, str, str]] = [
    ("Hemoglobin A1c", "%", "4.0-5.6"),
    ("Fasting Glucose", "mg/dL", "70-99"),
    ("Total Cholesterol", "mg/dL", "<200"),
    ("LDL Cholesterol", "mg/dL", "<100"),
    ("HDL Cholesterol", "mg/dL", ">40"),
    ("TSH", "uIU/mL", "0.4-4.0"),
    ("Creatinine", "mg/dL", "0.6-1.2"),
    ("Potassium", "mmol/L", "3.5-5.1"),
]


def _empty_result(document_id: str, doc_type: DocType) -> ExtractionResult:
    return ExtractionResult(
        document_id=document_id,
        doc_type=doc_type,
        doc_type_confidence=1.0,
        page_count=1,
        fields=[],
        overall_confidence=1.0,
    )


def generate_insurance_card(seed: int, document_id: str) -> GeneratedDocument:
    """A member ID card that fills the frame, as a scan or phone photo of one would.

    Card-shaped (landscape CR80), edge-to-edge, with the density a real card carries:
    a dark payer band, member/group identifiers, pharmacy routing numbers, and a
    customer-service footer. Deliberately *not* a card floating on a blank page.
    """
    rng = random.Random(seed)  # noqa: S311 - non-cryptographic use is intentional
    values = make_values(rng)

    img = Image.new("L", (CARD_W, CARD_H), color=255)
    draw = ImageDraw.Draw(img)
    font_payer = _font(64)
    font_kind = _font(34)
    font_label = _font(30)
    font_value = _font(38)
    font_small = _font(26)

    pad = 46
    band_h = 190

    # Outer card edge + dark payer band across the top.
    draw.rectangle([(4, 4), (CARD_W - 5, CARD_H - 5)], outline=0, width=6)
    draw.rectangle([(10, 10), (CARD_W - 11, band_h)], fill=45)
    draw.text((pad, 42), values.payer_name, font=font_payer, fill=255)
    draw.text((pad, 126), "HEALTH INSURANCE MEMBER ID CARD", font=font_kind, fill=225)

    # Left column: who the member is.
    left = [
        ("MEMBER NAME", values.member_name),
        ("MEMBER ID", values.member_id),
        ("GROUP NUMBER", values.plan_id),
        ("EFFECTIVE", f"01/01/{rng.choice((2025, 2026))}"),
    ]
    y = band_h + 56
    for label, value in left:
        draw.text((pad, y), label, font=font_label, fill=90)
        draw.text((pad, y + 38), value, font=font_value, fill=0)
        y += 146

    # Right column: pharmacy routing — the detail that makes a card unmistakably a card.
    right_x = CARD_W // 2 + 90
    right = [
        ("PLAN", rng.choice(["PPO", "HMO", "EPO", "POS"])),
        ("RxBIN", f"{rng.randint(100000, 999999)}"),
        ("RxPCN", rng.choice(["ADV", "MEDDADV", "CTRXMEDD", "A4"])),
        ("RxGRP", f"RX{rng.randint(1000, 9999)}"),
    ]
    y = band_h + 56
    for label, value in right:
        draw.text((right_x, y), label, font=font_label, fill=90)
        draw.text((right_x, y + 38), value, font=font_value, fill=0)
        y += 146

    # Footer strip: service + claims addresses, as printed on the real thing.
    footer_y = CARD_H - 118
    draw.line([(pad, footer_y - 22), (CARD_W - pad, footer_y - 22)], fill=120, width=3)
    draw.text((pad, footer_y), "Member Services 1-800-555-0142", font=font_small, fill=60)
    draw.text((right_x, footer_y), "Claims: PO Box 9000, Hartford CT", font=font_small, fill=60)
    draw.text(
        (pad, footer_y + 40),
        "Present this card at time of service.",
        font=font_small,
        fill=110,
    )

    return GeneratedDocument(
        image=img, labels=_empty_result(document_id, DocType.INSURANCE_CARD), values=values
    )


def generate_lab_report(seed: int, document_id: str) -> GeneratedDocument:
    """A table-heavy laboratory results page — visually distinct from both the card
    (dense, tabular) and the PA form (no label/value rows, a grid instead).
    """
    rng = random.Random(seed)  # noqa: S311 - non-cryptographic use is intentional
    values = make_values(rng)

    img = Image.new("L", (PAGE_W, PAGE_H), color=255)
    draw = ImageDraw.Draw(img)
    font_title = _font(46)
    font_label = _font(28)
    font_header = _font(26)
    font_cell = _font(26)

    draw.text((MARGIN, MARGIN), "LABORATORY RESULTS", font=font_title, fill=0)
    draw.text(
        (MARGIN, MARGIN + 60),
        f"Patient: {values.member_name}   DOB: {values.member_dob}",
        font=font_label,
        fill=50,
    )
    draw.line([(MARGIN, MARGIN + 110), (PAGE_W - MARGIN, MARGIN + 110)], fill=0, width=3)

    col_x = [MARGIN, MARGIN + 560, MARGIN + 900, MARGIN + 1260]
    headers = ["Test", "Result", "Reference Range", "Flag"]
    y = MARGIN + 160
    for x, header in zip(col_x, headers, strict=True):
        draw.text((x, y), header, font=font_header, fill=0)
    y += 44
    draw.line([(MARGIN, y), (PAGE_W - MARGIN, y)], fill=0, width=2)
    y += 20

    tests = rng.sample(_LAB_TESTS, k=6)
    for name, unit, ref_range in tests:
        result_value = f"{rng.uniform(0.5, 20.0):.1f} {unit}"
        draw.text((col_x[0], y), name, font=font_cell, fill=0)
        draw.text((col_x[1], y), result_value, font=font_cell, fill=0)
        draw.text((col_x[2], y), ref_range, font=font_cell, fill=0)
        draw.text((col_x[3], y), "Normal", font=font_cell, fill=60)
        y += 60

    return GeneratedDocument(
        image=img, labels=_empty_result(document_id, DocType.LAB_REPORT), values=values
    )
