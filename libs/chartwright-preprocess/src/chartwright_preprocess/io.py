"""Rasterize a raw upload into pages, before anything else in this library runs.

CP09 ingestion accepts PDF/PNG/JPEG/TIFF (``ingestion.validation.FileType``) — not page
images. Everything else in ``chartwright_preprocess`` operates on a ``list[Image.Image]``
of already-separated pages, so this is the first real step of the ``NORMALIZED`` stage:
turn the stored bytes into that list. PDF and multi-page TIFF (explicitly called out in
CP09's validation as "incl. multi-page fax") are the two formats that can already contain
more than one page before packet splitting ever runs.
"""

from __future__ import annotations

import io

import pypdfium2 as pdfium
from PIL import Image, ImageSequence

# Render DPI for PDF pages. 200 DPI matches chartwright_synthdata's synthetic page size
# (PAGE_W=1700 at ~200 DPI letter), so PDF-derived pages are comparable in scale to what
# the eval harness measures against.
_PDF_RENDER_DPI = 200


def load_pages(data: bytes, file_type: str) -> list[Image.Image]:
    """Return one Pillow image per page, in document order.

    ``file_type`` is the lowercase value from ``ingestion.validation.FileType``
    ("pdf" | "png" | "jpeg" | "tiff") — passed as a plain string rather than importing
    that enum, so this library has no dependency on the ingestion service.
    """
    if file_type == "pdf":
        return _load_pdf_pages(data)
    if file_type == "tiff":
        return _load_tiff_pages(data)
    if file_type in ("png", "jpeg"):
        return [Image.open(io.BytesIO(data)).convert("RGB")]
    msg = f"unsupported file_type for page loading: {file_type!r}"
    raise ValueError(msg)


def _load_pdf_pages(data: bytes) -> list[Image.Image]:
    scale = _PDF_RENDER_DPI / 72.0  # pdfium's native unit is 1/72 inch (a PDF "point")
    pdf = pdfium.PdfDocument(data)
    try:
        pages: list[Image.Image] = []
        for page in pdf:
            bitmap = page.render(scale=scale)
            pages.append(bitmap.to_pil().convert("RGB"))
            page.close()
        return pages
    finally:
        pdf.close()


def _load_tiff_pages(data: bytes) -> list[Image.Image]:
    img = Image.open(io.BytesIO(data))
    return [frame.convert("RGB") for frame in ImageSequence.Iterator(img)]


# Inverse of ingestion.validation's extension_for() mapping, duplicated rather than
# imported so this library has no dependency on the ingestion service — the pipeline
# activity that calls this only has a storage object key, e.g. ".../original.pdf".
_EXTENSION_TO_FILE_TYPE: dict[str, str] = {
    ".pdf": "pdf",
    ".png": "png",
    ".jpg": "jpeg",
    ".tiff": "tiff",
}


def file_type_from_extension(extension: str) -> str:
    """Map a stored object key's extension (as produced by ingestion's extension_for)
    to the ``file_type`` string ``load_pages`` expects. Raises on anything unrecognized
    rather than guessing."""
    try:
        return _EXTENSION_TO_FILE_TYPE[extension.lower()]
    except KeyError:
        msg = f"unrecognized file extension: {extension!r}"
        raise ValueError(msg) from None
