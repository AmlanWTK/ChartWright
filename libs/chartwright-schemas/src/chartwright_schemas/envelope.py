"""The document-level extraction envelope that moves through the pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from pydantic import BaseModel, Field, model_validator

from chartwright_schemas.documents import SCHEMA_REGISTRY, SCHEMA_VERSION
from chartwright_schemas.grounding import Confidence, GroundedField, GroundedTable
from chartwright_schemas.taxonomy import DocType


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


class ExtractionResult(BaseModel):
    """Everything extracted from one logical document, grounded and versioned.

    This is the contract between the AI core and everything downstream (validation,
    policy reasoning, review console, FHIR output). Consumers must tolerate additive
    changes; breaking changes bump ``schema_version`` major and run the eval gate.
    """

    document_id: str = Field(min_length=1)
    doc_type: DocType
    doc_type_confidence: Confidence
    schema_version: str = SCHEMA_VERSION
    page_count: Annotated[int, Field(ge=1)]
    fields: list[GroundedField] = Field(default_factory=list)
    tables: list[GroundedTable] = Field(default_factory=list)
    overall_confidence: Confidence
    needs_review: bool = False
    created_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _keys_belong_to_schema(self) -> ExtractionResult:
        """Field/table keys must exist in the registered schema for this doc type.

        Guards against extractor drift: a model inventing a key it wasn't asked for is a
        contract violation, caught at the boundary rather than downstream.
        """
        schema = SCHEMA_REGISTRY.get(self.doc_type)
        if schema is None:  # unstructured types carry no typed fields
            if self.fields or self.tables:
                msg = f"doc_type '{self.doc_type}' has no schema; fields/tables must be empty"
                raise ValueError(msg)
            return self
        allowed_fields = schema.field_keys()
        for f in self.fields:
            if f.key not in allowed_fields:
                msg = f"unknown field key '{f.key}' for doc_type '{self.doc_type}'"
                raise ValueError(msg)
        allowed_tables = {t.key for t in schema.tables}
        for t in self.tables:
            if t.key not in allowed_tables:
                msg = f"unknown table key '{t.key}' for doc_type '{self.doc_type}'"
                raise ValueError(msg)
        return self

    @model_validator(mode="after")
    def _pages_within_document(self) -> ExtractionResult:
        for f in self.fields:
            if f.provenance.page > self.page_count:
                msg = (
                    f"field '{f.key}' cites page {f.provenance.page} > page_count {self.page_count}"
                )
                raise ValueError(msg)
        for t in self.tables:
            if t.page > self.page_count:
                msg = f"table '{t.key}' cites page {t.page} > page_count {self.page_count}"
                raise ValueError(msg)
        return self
