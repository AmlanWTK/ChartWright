"""How long does NORMALIZED actually take, per page? Run when a stage times out.

CP15's fan-out test failed with the activity CANCELLED inside detect_skew -- the
signature of Temporal's start_to_close_timeout, not of a logic error. The suspicion is
that normalization cost is linear in page count against a fixed 30s budget, so any
document past ~2 pages cannot complete the stage. This measures that instead of
inferring it, and sizes the fix from data.

Run:  uv run python scripts/diag_normalize_timing.py
"""

from __future__ import annotations

import io
import time
import uuid

from chartwright_preprocess import detect_orientation, detect_skew, load_pages, normalize_page
from chartwright_synthdata import generate_prior_auth
from chartwright_synthdata.classify_docs import generate_insurance_card
from PIL import Image, ImageDraw

_STAGE_TIMEOUT_S = 30.0  # the current start_to_close_timeout in workflows.py


def _pages(*, resolution: float | None) -> list[Image.Image]:
    """The fan-out fixture's three pages, through the same PDF path.

    ``resolution`` is PIL's PDF save DPI, and it decides the page BOX. At 200 it matches
    ``_PDF_RENDER_DPI`` and the round trip preserves scale. At None (PIL's 72 DPI
    default) the box becomes 1700x2200 *points* and pdfium renders 4723x6112 -- the
    pathological case, kept here because a real PDF with an odd page box does the same
    thing and this is the only place that quantifies it.
    """
    doc_id = str(uuid.uuid4())
    form = generate_prior_auth(seed=7, document_id=doc_id).image.convert("RGB")
    card = generate_insurance_card(seed=7, document_id=doc_id).image.convert("RGB")
    separator = Image.new("RGB", form.size, "white")
    ImageDraw.Draw(separator).line(
        [(200, form.height // 2), (600, form.height // 2)], fill=(190, 190, 190), width=2
    )
    buf = io.BytesIO()
    kwargs = {"resolution": resolution} if resolution else {}
    form.save(buf, format="PDF", save_all=True, append_images=[separator, card], **kwargs)
    return load_pages(buf.getvalue(), "pdf")


def _time(label: str, fn) -> float:  # type: ignore[no-untyped-def]
    start = time.perf_counter()
    fn()
    elapsed = time.perf_counter() - start
    print(f"    {label:<22} {elapsed:6.2f}s")
    return elapsed


def main() -> None:
    print("=" * 68)
    print("BASELINE — one PNG page (what every passing test does today)")
    print("=" * 68)
    single = generate_prior_auth(seed=7, document_id=str(uuid.uuid4())).image
    print(f"  size {single.size}")
    baseline = _time("normalize_page", lambda: normalize_page(single))

    print()
    print("=" * 68)
    print("THE FAN-OUT FIXTURE — three pages, PDF saved at 200 DPI (correct)")
    print("=" * 68)
    pages = _pages(resolution=200.0)
    names = ["prior-auth form", "blank separator", "insurance card"]
    total = 0.0
    for name, page in zip(names, pages, strict=False):
        print(f"  page: {name}  size {page.size}  mode {page.mode}")
        _time("detect_orientation", lambda p=page: detect_orientation(p))  # type: ignore[misc]
        _time("detect_skew", lambda p=page: detect_skew(p))  # type: ignore[misc]
        total += _time("normalize_page (total)", lambda p=page: normalize_page(p))  # type: ignore[misc]
        print()

    print("=" * 68)
    print("VERDICT")
    print("=" * 68)
    print(f"  one page              : {baseline:6.2f}s")
    print(f"  three pages           : {total:6.2f}s")
    print(f"  current stage timeout : {_STAGE_TIMEOUT_S:6.2f}s")
    print()
    if total > _STAGE_TIMEOUT_S:
        print("  => CONFIRMED: three pages exceed the stage timeout. The cancellation")
        print("     was the timeout, not a fan-out bug.")
    else:
        print("  => NOT CONFIRMED: normalization fits inside the timeout, so the")
        print("     cancellation came from something else. Do not 'fix' the timeout.")
    per_page = total / max(len(pages), 1)
    print()
    print(f"  cost per page ~{per_page:.2f}s  ->  the timeout caps a document at")
    print(f"  ~{int(_STAGE_TIMEOUT_S // max(per_page, 0.01))} pages. Real faxes run 5-30.")

    print()
    print("=" * 68)
    print("PATHOLOGICAL PAGE BOX — same content, PDF saved at PIL's 72 DPI default")
    print("=" * 68)
    print("  A PDF whose page box is not physically letter-sized renders enormous at")
    print("  _PDF_RENDER_DPI. load_pages caps nothing, so this is what a real upload")
    print("  with an odd box would cost.")
    big = _pages(resolution=None)[0]
    print(f"  page size {big.size}  ({big.width * big.height / 1e6:.1f} MP)")
    inflated = _time("normalize_page (1 page)", lambda: normalize_page(big))
    print()
    print(f"  one page at that scale : {inflated:6.2f}s   vs {total / 3:.2f}s at 200 DPI")
    print(
        f"  => a single such page {'EXCEEDS' if inflated > _STAGE_TIMEOUT_S else 'fits in'} "
        f"the {_STAGE_TIMEOUT_S:.0f}s stage timeout."
    )
    print()
    print("Paste the whole output back.")


if __name__ == "__main__":
    main()
