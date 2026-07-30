"""Tests: determinism, schema conformance, label accuracy, degradation behavior."""

import random

from chartwright_schemas import SCHEMA_REGISTRY, DocType, ExtractionResult
from chartwright_synthdata import Degradation, degrade, generate_prior_auth, make_values
from chartwright_synthdata.values import make_npi


class TestValues:
    def test_deterministic_for_same_seed(self) -> None:
        v1 = make_values(random.Random(123))
        v2 = make_values(random.Random(123))
        assert v1 == v2

    def test_different_seeds_differ(self) -> None:
        v1 = make_values(random.Random(1))
        v2 = make_values(random.Random(2))
        assert v1 != v2

    def test_npi_passes_luhn(self) -> None:
        """Generated NPIs must pass the standard checksum so CP16's validator accepts them."""
        rng = random.Random(99)
        for _ in range(50):
            npi = make_npi(rng)
            assert len(npi) == 10
            digits = [int(c) for c in "80840" + npi]
            total = 0
            for i, d in enumerate(reversed(digits)):
                if i % 2 == 1:
                    d *= 2
                    if d > 9:
                        d -= 9
                total += d
            assert total % 10 == 0, f"NPI {npi} fails checksum"


class TestGenerator:
    def test_deterministic_output(self) -> None:
        a = generate_prior_auth(seed=7, document_id="pa_x")
        b = generate_prior_auth(seed=7, document_id="pa_x")
        assert a.values == b.values
        # created_at is wall-clock metadata, not content — determinism covers content.
        assert a.labels.model_dump(exclude={"created_at"}) == b.labels.model_dump(
            exclude={"created_at"}
        )
        assert list(a.image.getdata()) == list(b.image.getdata())

    def test_labels_are_schema_conformant(self) -> None:
        doc = generate_prior_auth(seed=11, document_id="pa_y")
        # Round-trip through JSON proves the labels validate as an ExtractionResult.
        parsed = ExtractionResult.model_validate_json(doc.labels.model_dump_json())
        assert parsed.doc_type == DocType.PRIOR_AUTH_REQUEST

    def test_all_required_schema_fields_present(self) -> None:
        doc = generate_prior_auth(seed=11, document_id="pa_y")
        produced = {f.key for f in doc.labels.fields}
        schema = SCHEMA_REGISTRY[DocType.PRIOR_AUTH_REQUEST]
        required = {
            f.key for f in schema.fields if f.required and f.key != "clinical_justification"
        }
        assert required <= produced

    def test_bboxes_within_page(self) -> None:
        doc = generate_prior_auth(seed=3, document_id="pa_z")
        w, h = doc.image.size
        for f in doc.labels.fields:
            box = f.provenance.bbox
            assert 0 <= box.x < w
            assert 0 <= box.y < h
            assert box.x + box.w <= w
            assert box.y + box.h <= h

    def test_bbox_contains_ink(self) -> None:
        """Each ground-truth bbox must actually contain dark pixels (the printed value)."""
        doc = generate_prior_auth(seed=5, document_id="pa_ink")
        for f in doc.labels.fields:
            box = f.provenance.bbox
            region = doc.image.crop(
                (int(box.x), int(box.y), int(box.x + box.w), int(box.y + box.h))
            )
            assert min(region.getdata()) < 128, f"bbox for '{f.key}' contains no ink"


class TestDegradation:
    def test_clean_is_identity(self) -> None:
        doc = generate_prior_auth(seed=21, document_id="pa_c")
        img, labels = degrade(doc.image, doc.labels, Degradation.CLEAN, seed=21)
        assert img is doc.image
        assert labels is doc.labels

    def test_degraded_labels_still_validate(self) -> None:
        doc = generate_prior_auth(seed=22, document_id="pa_d")
        for level in (Degradation.FAX, Degradation.BAD_FAX):
            _, labels = degrade(doc.image, doc.labels, level, seed=22)
            ExtractionResult.model_validate(labels.model_dump())

    def test_degraded_bboxes_still_contain_ink(self) -> None:
        """The label-preservation guarantee: after skew, boxes still cover their text."""
        doc = generate_prior_auth(seed=23, document_id="pa_e")
        img, labels = degrade(doc.image, doc.labels, Degradation.BAD_FAX, seed=23)
        w, h = img.size
        for f in labels.fields:
            box = f.provenance.bbox
            x0, y0 = max(int(box.x), 0), max(int(box.y), 0)
            x1, y1 = min(int(box.x + box.w), w), min(int(box.y + box.h), h)
            assert x1 > x0 and y1 > y0, f"bbox for '{f.key}' collapsed after degradation"
            region = img.crop((x0, y0, x1, y1))
            assert min(region.getdata()) < 128, f"bbox for '{f.key}' lost its ink after skew"

    def test_degradation_is_deterministic(self) -> None:
        doc = generate_prior_auth(seed=24, document_id="pa_f")
        img1, l1 = degrade(doc.image, doc.labels, Degradation.FAX, seed=24)
        img2, l2 = degrade(doc.image, doc.labels, Degradation.FAX, seed=24)
        assert list(img1.getdata()) == list(img2.getdata())
        assert l1.model_dump() == l2.model_dump()
