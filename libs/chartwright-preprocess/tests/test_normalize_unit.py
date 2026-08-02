"""Unit tests: orientation + skew detection against fabricated and rendered pages."""

import random

from chartwright_preprocess import NormalizedPage, detect_orientation, detect_skew, normalize_page
from chartwright_synthdata import generate_prior_auth


class TestOrientation:
    def test_upright_page_needs_no_correction(self) -> None:
        g = generate_prior_auth(seed=1, document_id="d")
        assert detect_orientation(g.image) == 0

    def test_each_rotation_detected_correctly(self) -> None:
        g = generate_prior_auth(seed=2, document_id="d")
        for angle in (0, 90, 180, 270):
            rotated = g.image.rotate(angle, expand=True, fillcolor=255)
            assert detect_orientation(rotated) == angle

    def test_upside_down_is_not_confused_with_upright(self) -> None:
        """The 0-vs-180 tie-break is the property most likely to silently regress."""
        g = generate_prior_auth(seed=3, document_id="d")
        flipped = g.image.rotate(180, expand=True, fillcolor=255)
        assert detect_orientation(flipped) == 180


class TestSkew:
    def test_unskewed_page_needs_minimal_correction(self) -> None:
        g = generate_prior_auth(seed=4, document_id="d")
        assert abs(detect_skew(g.image)) < 0.5

    def test_tilted_page_recovers_the_opposite_angle(self) -> None:
        g = generate_prior_auth(seed=5, document_id="d")
        rng = random.Random(5)
        true_skew = rng.uniform(-3.0, 3.0)
        tilted = g.image.rotate(true_skew, expand=False, fillcolor=255)
        detected = detect_skew(tilted)
        # detect_skew returns the correction angle: applying it should undo true_skew.
        assert abs(detected - (-true_skew)) < 0.5


class TestNormalizePage:
    def test_returns_recoverable_transform_params(self) -> None:
        g = generate_prior_auth(seed=6, document_id="d")
        result = normalize_page(g.image)
        assert isinstance(result, NormalizedPage)
        assert result.rotation_deg in (0, 90, 180, 270)
        assert isinstance(result.skew_angle_deg, float)
        assert result.contrast_factor > 0

    def test_upright_clean_page_applies_no_rotation(self) -> None:
        g = generate_prior_auth(seed=7, document_id="d")
        result = normalize_page(g.image)
        assert result.rotation_deg == 0

    def test_rotated_page_reports_the_correction_applied(self) -> None:
        g = generate_prior_auth(seed=8, document_id="d")
        rotated = g.image.rotate(90, expand=True, fillcolor=255)
        result = normalize_page(rotated)
        assert result.rotation_deg == 90

    def test_output_image_has_content(self) -> None:
        """Sanity: normalization must not blank the page out."""
        g = generate_prior_auth(seed=9, document_id="d")
        result = normalize_page(g.image)
        assert result.image.size[0] > 0
        assert min(result.image.getdata()) < 128  # some ink survives
