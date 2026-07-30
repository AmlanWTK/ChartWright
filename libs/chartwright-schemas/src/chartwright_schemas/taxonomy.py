"""The v1 clinical document taxonomy (CP03).

Classification (CP14) assigns exactly one ``DocType`` per logical document. The taxonomy is
deliberately small and stable; per-tenant custom types extend it via configuration later,
and anything unrecognized lands in ``OTHER`` (which always routes to human review).
"""

from __future__ import annotations

from enum import StrEnum


class DocType(StrEnum):
    """Document types Chartwright understands in v1."""

    PRIOR_AUTH_REQUEST = "prior_auth_request"
    REFERRAL = "referral"
    EOB = "eob"
    LAB_REPORT = "lab_report"
    DISCHARGE_SUMMARY = "discharge_summary"
    CLINICAL_NOTE = "clinical_note"
    INSURANCE_CARD = "insurance_card"
    ID_DOCUMENT = "id_document"
    OTHER = "other"


# Types with a structured extraction schema in v1. The remaining types get full-text OCR +
# classification only (their structured schemas arrive post-v1).
STRUCTURED_TYPES: frozenset[DocType] = frozenset(
    {
        DocType.PRIOR_AUTH_REQUEST,
        DocType.REFERRAL,
        DocType.EOB,
        DocType.LAB_REPORT,
        DocType.INSURANCE_CARD,
    }
)

# Types that ALWAYS route to human review regardless of confidence.
ALWAYS_REVIEW_TYPES: frozenset[DocType] = frozenset({DocType.OTHER, DocType.ID_DOCUMENT})
