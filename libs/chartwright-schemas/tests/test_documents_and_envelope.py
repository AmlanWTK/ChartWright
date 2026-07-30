"""Tests for the schema registry and the ExtractionResult envelope."""

import pytest
from chartwright_schemas import (
    SCHEMA_REGISTRY,
    STRUCTURED_TYPES,
    BoundingBox,
    DocType,
    ExtractionResult,
    GroundedField,
    Provenance,
)
from pydantic import ValidationError


def make_field(key: str, page: int = 1) -> GroundedField:
    return GroundedField(
        key=key,
        value_raw="A1234567",
        confidence=0.94,
        provenance=Provenance(
            page=page,
            bbox=BoundingBox(x=10, y=20, w=100, h=18),
            source_span="Member ID: A1234567",
        ),
    )


class TestRegistry:
    def test_every_structured_type_has_a_schema(self) -> None:
        assert set(SCHEMA_REGISTRY) == set(STRUCTURED_TYPES)

    def test_every_schema_has_critical_fields(self) -> None:
        """Every structured type must declare at least one critical field —
        otherwise the 95% accuracy NFR has nothing to bind to."""
        for doc_type, schema in SCHEMA_REGISTRY.items():
            assert schema.critical_keys(), f"{doc_type} has no critical fields"

    def test_field_keys_unique_per_schema(self) -> None:
        for schema in SCHEMA_REGISTRY.values():
            keys = [f.key for f in schema.fields]
            assert len(keys) == len(set(keys))

    def test_prior_auth_has_expected_critical_fields(self) -> None:
        crit = SCHEMA_REGISTRY[DocType.PRIOR_AUTH_REQUEST].critical_keys()
        assert {
            "member_id",
            "ordering_provider_npi",
            "diagnosis_code",
            "procedure_code",
            "date_of_service",
        } <= crit


class TestExtractionResult:
    def test_valid_envelope(self) -> None:
        result = ExtractionResult(
            document_id="doc_123",
            doc_type=DocType.PRIOR_AUTH_REQUEST,
            doc_type_confidence=0.98,
            page_count=3,
            fields=[make_field("member_id")],
            overall_confidence=0.92,
        )
        assert result.schema_version == "1.0.0"

    def test_unknown_field_key_rejected(self) -> None:
        """Extractor drift guard: a key not in the schema is a contract violation."""
        with pytest.raises(ValidationError, match="unknown field key"):
            ExtractionResult(
                document_id="doc_123",
                doc_type=DocType.PRIOR_AUTH_REQUEST,
                doc_type_confidence=0.98,
                page_count=1,
                fields=[make_field("not_a_real_field")],
                overall_confidence=0.9,
            )

    def test_field_citing_page_beyond_document_rejected(self) -> None:
        with pytest.raises(ValidationError, match="page 5 > page_count 2"):
            ExtractionResult(
                document_id="doc_123",
                doc_type=DocType.PRIOR_AUTH_REQUEST,
                doc_type_confidence=0.98,
                page_count=2,
                fields=[make_field("member_id", page=5)],
                overall_confidence=0.9,
            )

    def test_unstructured_type_must_have_no_fields(self) -> None:
        with pytest.raises(ValidationError, match="has no schema"):
            ExtractionResult(
                document_id="doc_123",
                doc_type=DocType.CLINICAL_NOTE,
                doc_type_confidence=0.9,
                page_count=1,
                fields=[make_field("member_id")],
                overall_confidence=0.9,
            )

    def test_unstructured_type_with_empty_fields_ok(self) -> None:
        result = ExtractionResult(
            document_id="doc_123",
            doc_type=DocType.CLINICAL_NOTE,
            doc_type_confidence=0.9,
            page_count=1,
            overall_confidence=0.9,
        )
        assert result.fields == []
