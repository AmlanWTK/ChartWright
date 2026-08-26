"""Unit tests: description -> DocType mapping and the OTHER-on-failure safety net.

Uses chartwright_gateway's own MockProvider (a scripted-response test double already
built for CP11) rather than hitting a live Ollama server — no network needed.

CP14 classifies by describe-then-map (see classifier.py's module docstring): the model
returns a free-text description of the page and the taxonomy mapping happens in
deterministic code. These tests therefore exercise the mapper directly, plus the
end-to-end path through a scripted gateway.
"""

import pytest
from chartwright_classify import classify_packet
from chartwright_classify.classifier import ClassificationResult, map_description
from chartwright_gateway import ModelGateway
from chartwright_gateway.providers import MockProvider
from chartwright_schemas.taxonomy import DocType
from PIL import Image

_PAGE = Image.new("RGB", (100, 140), color="white")

# A real moondream description, captured during CP14 verification. Kept verbatim so the
# tests are anchored to observed model output rather than to prose invented to pass.
_REAL_PA_DESCRIPTION = (
    "\nThe image shows a page of text that appears to be a request for prior "
    "authorization, likely related to a medical or healthcare context. The text is "
    "written in black ink and is organized into multiple columns with headings."
)


def _gateway(response_text: str) -> ModelGateway:
    return ModelGateway(tier_chains={0: [MockProvider(response=response_text)]})


class TestMapping:
    @pytest.mark.parametrize(
        ("description", "expected"),
        [
            (_REAL_PA_DESCRIPTION, DocType.PRIOR_AUTH_REQUEST),
            ("A specialist referral letter for a cardiology consult.", DocType.REFERRAL),
            ("An explanation of benefits showing claim lines.", DocType.EOB),
            ("Laboratory results with a reference range column.", DocType.LAB_REPORT),
            ("A hospital discharge summary for the patient.", DocType.DISCHARGE_SUMMARY),
            ("An office visit progress note.", DocType.CLINICAL_NOTE),
            ("A health insurance member ID card with RxBIN.", DocType.INSURANCE_CARD),
            ("A state-issued driver's license.", DocType.ID_DOCUMENT),
        ],
    )
    def test_each_type_is_recognized(self, description: str, expected: DocType) -> None:
        doc_type, confidence = map_description(description)
        assert doc_type == expected
        assert 0.0 < confidence <= 1.0

    def test_matching_is_case_insensitive(self) -> None:
        assert map_description("PRIOR AUTHORIZATION REQUEST")[0] == DocType.PRIOR_AUTH_REQUEST

    def test_unambiguous_description_scores_full_confidence(self) -> None:
        _, confidence = map_description("Laboratory results report.")
        assert confidence == 1.0

    def test_mixed_evidence_is_downweighted(self) -> None:
        """A description naming two types must not claim certainty about either."""
        doc_type, confidence = map_description(
            "A prior authorization form listing insurance and group number details."
        )
        assert doc_type == DocType.PRIOR_AUTH_REQUEST
        assert confidence < 1.0

    def test_specific_phrase_beats_incidental_word(self) -> None:
        """'insurance card' must win over the bare word 'insurance'."""
        assert map_description("An insurance card.")[0] == DocType.INSURANCE_CARD

    def test_mapping_is_deterministic(self) -> None:
        assert map_description(_REAL_PA_DESCRIPTION) == map_description(_REAL_PA_DESCRIPTION)


class TestOtherFallback:
    """Anything unrecognizable must land in OTHER at 0.0 — never a guess, never a raise.

    OTHER is in ALWAYS_REVIEW_TYPES, so this is the path that routes a page a human has
    to look at. Getting it wrong would silently swallow documents.
    """

    @pytest.mark.parametrize(
        "description",
        [
            "",
            "   \n  ",
            "ids",  # observed: what the model returned under the old long prompt
            "The image shows a blank white page with black text and numbers.",
            "asdfgh qwerty zxcvbn",
            '{"doc_type": "xray", "confidence": 0.9}',  # a type outside the nine
        ],
    )
    def test_unrecognizable_description_maps_to_other(self, description: str) -> None:
        doc_type, confidence = map_description(description)
        assert doc_type == DocType.OTHER
        assert confidence == 0.0


class TestClassifyPacket:
    def test_end_to_end_through_scripted_gateway(self) -> None:
        result = classify_packet(_PAGE, gateway=_gateway(_REAL_PA_DESCRIPTION), tenant_id="t1")
        assert isinstance(result, ClassificationResult)
        assert result.doc_type == DocType.PRIOR_AUTH_REQUEST
        assert result.confidence == 1.0

    def test_raw_description_is_preserved_for_audit(self) -> None:
        result = classify_packet(_PAGE, gateway=_gateway(_REAL_PA_DESCRIPTION), tenant_id="t1")
        assert result.raw_text == _REAL_PA_DESCRIPTION

    @pytest.mark.parametrize("response_text", ["", "ids", "!!!", "a" * 4000])
    def test_never_raises_on_hostile_model_output(self, response_text: str) -> None:
        result = classify_packet(_PAGE, gateway=_gateway(response_text), tenant_id="t1")
        assert result.doc_type == DocType.OTHER
        assert result.confidence == 0.0
        assert result.raw_text == response_text

    def test_grayscale_page_is_converted_not_rejected(self) -> None:
        """CP13 hands over mode-'L' pages; classify_packet must not choke on them."""
        grayscale = Image.new("L", (80, 100), color=255)
        result = classify_packet(grayscale, gateway=_gateway("Lab report."), tenant_id="t1")
        assert result.doc_type == DocType.LAB_REPORT
