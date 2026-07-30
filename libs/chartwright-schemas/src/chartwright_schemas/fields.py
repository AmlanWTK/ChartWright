"""Field metadata: the declarative description of what each document type contains.

An extraction schema is a list of ``FieldSpec`` (+ ``TableSpec``) — this is what the
schema-constrained extractor (CP15) is prompted with, what validation (CP16) enforces,
and what the review console (CP24) renders. Keeping specs declarative (data, not code)
lets per-tenant custom types be configuration.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class FieldKind(StrEnum):
    """Value kinds the validator layer (CP16) knows how to normalize/verify."""

    TEXT = "text"
    DATE = "date"  # normalized to ISO 8601
    PHONE = "phone"
    NPI = "npi"  # 10-digit with Luhn-like checksum
    ICD10 = "icd10"
    CPT = "cpt"
    MEMBER_ID = "member_id"
    CHECKBOX = "checkbox"  # normalized to "true"/"false"
    NUMBER = "number"


class FieldSpec(BaseModel):
    """Declares one extractable field for a document type."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    label: str = Field(min_length=1, description="Human label as typically printed on forms.")
    kind: FieldKind
    required: bool = True
    critical: bool = Field(
        default=False,
        description="Critical fields carry the 95% accuracy target and stricter review routing.",
    )


class TableSpec(BaseModel):
    """Declares one extractable table for a document type."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    columns: tuple[str, ...] = Field(min_length=1, description="Expected column headers, in order.")
    required: bool = False
