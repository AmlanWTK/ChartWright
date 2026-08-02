"""Synthetic multi-document packets, for testing CP13's packet splitter.

Composes visually distinct synthetic pages into one page sequence with recorded ground
truth boundaries — the analogue of ``generator.py``'s pixel-accurate labels, but for
document *boundaries* rather than field values. Three page "shapes" are used so
adjacent sub-documents in a packet are structurally distinguishable without needing a
second real document template: a full form (``generate_prior_auth``), a sparse
card-like page (few short lines, mimicking an insurance card photo), and a blank fax
separator sheet.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from PIL import Image, ImageDraw

from chartwright_synthdata.generator import PAGE_H, PAGE_W, _font, generate_prior_auth
from chartwright_synthdata.values import make_values


def generate_sparse_page(seed: int) -> Image.Image:
    """A short page with a filled header band: a handful of lines in the upper-center
    third, plus a solid card-style header bar.

    Stands in for a photographed insurance card or a brief cover note — genuinely
    different ink density and layout from both a dense form page and a truly blank fax
    separator. The filled header bar is deliberate: text alone at this line count sits
    below a realistic blank-page threshold (~0.4% ink), which is indistinguishable from
    scanner noise on an actually-blank sheet; a card-like solid band is closer to how a
    real insurance-card photo (which has color/logo blocks, not just text) would score.
    """
    rng = random.Random(seed)  # noqa: S311 - non-cryptographic use is intentional
    values = make_values(rng)
    img = Image.new("L", (PAGE_W, PAGE_H), color=255)
    draw = ImageDraw.Draw(img)
    font = _font(40)
    x = PAGE_W // 4
    top = PAGE_H // 3 - 40

    header_h = 90
    draw.rectangle([(x - 40, top), (x + 680, top + header_h)], fill=40)
    draw.text((x - 10, top + 20), values.payer_name, font=font, fill=255)

    lines = [
        f"Member: {values.member_name}",
        f"ID: {values.member_id}",
        f"Group: {values.plan_id}",
    ]
    y = top + header_h + 30
    for line in lines:
        draw.text((x, y), line, font=font, fill=0)
        y += 66
    draw.rectangle([(x - 40, top), (x + 680, y + 20)], outline=100, width=3)
    return img


def generate_blank_page() -> Image.Image:
    """A near-empty separator page, as fax transmissions commonly insert between docs."""
    return Image.new("L", (PAGE_W, PAGE_H), color=255)


@dataclass(frozen=True)
class SyntheticPacketSet:
    """A composed page sequence plus ground-truth document boundaries.

    ``boundaries`` gives, for each logical sub-document, the tuple of page indices
    (into ``pages``, 0-based) that belong to it — content pages only, blank separators
    excluded, matching ``chartwright_preprocess.splitting.Packet.page_indices``.
    """

    pages: list[Image.Image]
    boundaries: list[tuple[int, ...]]


def compose_packet_set(
    seed: int,
    *,
    n_docs: int = 3,
    use_blank_separators: bool = True,
) -> SyntheticPacketSet:
    """Concatenate ``n_docs`` visually distinct synthetic sub-documents into one upload.

    Each sub-document is one page, alternating "form" and "sparse card" shapes so
    consecutive documents are structurally distinguishable. When
    ``use_blank_separators`` is True, a blank page is inserted between every pair of
    sub-documents (the common real-world fax case); when False, sub-documents sit
    directly adjacent, exercising the structural-discontinuity path instead of the
    blank-page path.
    """
    pages: list[Image.Image] = []
    boundaries: list[tuple[int, ...]] = []

    for doc_i in range(n_docs):
        doc_seed = seed * 100 + doc_i
        if doc_i % 2 == 0:
            page = generate_prior_auth(seed=doc_seed, document_id=f"pk{doc_seed}").image
        else:
            page = generate_sparse_page(seed=doc_seed)

        if doc_i > 0 and use_blank_separators:
            pages.append(generate_blank_page())

        start = len(pages)
        pages.append(page)
        boundaries.append((start,))

    return SyntheticPacketSet(pages=pages, boundaries=boundaries)
