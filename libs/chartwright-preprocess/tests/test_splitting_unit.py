"""Unit tests: packet splitting against fabricated pages and synthetic packets."""

from chartwright_preprocess import HeuristicSplitter, Packet, PageFeatures, page_features
from chartwright_synthdata import generate_prior_auth
from chartwright_synthdata.packets import (
    compose_packet_set,
    generate_blank_page,
    generate_sparse_page,
)
from PIL import Image


def _blank() -> Image.Image:
    return Image.new("L", (200, 260), color=255)


def _dense() -> Image.Image:
    img = Image.new("L", (200, 260), color=255)
    for y in range(0, 260, 4):
        for x in range(0, 200, 2):
            img.putpixel((x, y), 0)
    return img


class TestPageFeatures:
    def test_blank_page_has_near_zero_ink_density(self) -> None:
        f = page_features(_blank())
        assert f.is_blank
        assert f.ink_density == 0.0

    def test_dense_page_is_not_blank(self) -> None:
        f = page_features(_dense())
        assert not f.is_blank
        assert f.ink_density > 0.1

    def test_synthetic_form_page_is_not_blank(self) -> None:
        g = generate_prior_auth(seed=10, document_id="d")
        f = page_features(g.image)
        assert isinstance(f, PageFeatures)
        assert not f.is_blank

    def test_synthetic_sparse_page_clears_the_blank_threshold(self) -> None:
        """Regression guard: a prior tuning pass had this page misclassified as blank."""
        f = page_features(generate_sparse_page(seed=11))
        assert not f.is_blank


class TestHeuristicSplitter:
    def test_empty_input_returns_no_packets(self) -> None:
        assert HeuristicSplitter().split([]) == []

    def test_single_page_is_one_packet(self) -> None:
        g = generate_prior_auth(seed=12, document_id="d")
        result = HeuristicSplitter().split([g.image])
        assert result == [Packet(page_indices=(0,), boundary_score=0.0)]

    def test_blank_separator_splits_into_two_packets(self) -> None:
        g1 = generate_prior_auth(seed=13, document_id="a")
        g2 = generate_prior_auth(seed=14, document_id="b")
        pages = [g1.image, generate_blank_page(), g2.image]
        result = HeuristicSplitter().split(pages)
        assert [p.page_indices for p in result] == [(0,), (2,)]

    def test_blank_pages_never_appear_inside_a_packet(self) -> None:
        g1 = generate_prior_auth(seed=15, document_id="a")
        g2 = generate_prior_auth(seed=16, document_id="b")
        pages = [g1.image, generate_blank_page(), g2.image]
        result = HeuristicSplitter().split(pages)
        for packet in result:
            assert 1 not in packet.page_indices

    def test_structurally_distinct_adjacent_pages_split_without_a_blank(self) -> None:
        g = generate_prior_auth(seed=17, document_id="a")
        sparse = generate_sparse_page(seed=18)
        result = HeuristicSplitter().split([g.image, sparse])
        assert [p.page_indices for p in result] == [(0,), (1,)]

    def test_all_pages_blank_yields_no_packets(self) -> None:
        result = HeuristicSplitter().split([generate_blank_page(), generate_blank_page()])
        assert result == []


class TestSyntheticPacketSetGroundTruth:
    """The eval harness (scripts/eval_preprocess.py) depends on this generator being
    self-consistent — a bug here would make the eval measure against wrong ground truth."""

    def test_boundaries_cover_every_content_page_exactly_once(self) -> None:
        pk = compose_packet_set(seed=100, n_docs=3, use_blank_separators=True)
        covered = sorted(i for b in pk.boundaries for i in b)
        content_indices = [i for i, p in enumerate(pk.pages) if not page_features(p).is_blank]
        assert covered == sorted(content_indices)

    def test_no_blank_separators_variant_has_no_blank_pages(self) -> None:
        pk = compose_packet_set(seed=101, n_docs=3, use_blank_separators=False)
        assert all(not page_features(p).is_blank for p in pk.pages)
