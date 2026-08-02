"""Unit tests: rasterizing raw upload bytes into pages (PDF/PNG/JPEG/TIFF)."""

import io

import pytest
from chartwright_preprocess import load_pages
from chartwright_synthdata import generate_prior_auth
from PIL import Image


def _page(seed: int) -> Image.Image:
    return generate_prior_auth(seed=seed, document_id=f"d{seed}").image.convert("RGB")


class TestLoadPages:
    def test_png_is_a_single_page(self) -> None:
        buf = io.BytesIO()
        _page(1).save(buf, format="PNG")
        pages = load_pages(buf.getvalue(), "png")
        assert len(pages) == 1
        assert pages[0].size == (1700, 2200)

    def test_jpeg_is_a_single_page(self) -> None:
        buf = io.BytesIO()
        _page(2).save(buf, format="JPEG")
        pages = load_pages(buf.getvalue(), "jpeg")
        assert len(pages) == 1

    def test_multipage_tiff_yields_all_pages_in_order(self) -> None:
        p1, p2, p3 = _page(3), _page(4), _page(5)
        buf = io.BytesIO()
        p1.save(buf, format="TIFF", save_all=True, append_images=[p2, p3])
        pages = load_pages(buf.getvalue(), "tiff")
        assert len(pages) == 3
        assert all(p.size == (1700, 2200) for p in pages)

    def test_multipage_pdf_yields_all_pages_at_the_source_resolution(self) -> None:
        p1, p2 = _page(6), _page(7)
        buf = io.BytesIO()
        p1.save(buf, format="PDF", save_all=True, append_images=[p2], resolution=200.0)
        pages = load_pages(buf.getvalue(), "pdf")
        assert len(pages) == 2
        assert pages[0].size == (1700, 2200)

    def test_unsupported_file_type_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported"):
            load_pages(b"whatever", "bmp")
