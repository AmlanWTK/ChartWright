"""Per-document-type extraction schemas (CP03) and the schema registry.

Each ``DocSchema`` declares the fields/tables for one ``DocType``. These specs drive:
- extraction prompts + JSON-schema constraints (CP15),
- deterministic validation (CP16),
- review-console rendering (CP24),
- gold-set structure for the eval harness (CP26).

Design notes
------------
* ``critical=True`` marks the fields under the 95%-accuracy NFR (member ID, codes, dates,
  NPIs) — errors here cause denials.
* Schemas are versioned via ``ExtractionResult.schema_version``; adding a field is a minor
  bump, changing/removing one is a major bump and an eval-gate run.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from chartwright_schemas.fields import FieldKind, FieldSpec, TableSpec
from chartwright_schemas.taxonomy import DocType

SCHEMA_VERSION = "1.0.0"


class DocSchema(BaseModel):
    """The full extraction schema for one document type."""

    model_config = ConfigDict(frozen=True)

    doc_type: DocType
    version: str = SCHEMA_VERSION
    fields: tuple[FieldSpec, ...]
    tables: tuple[TableSpec, ...] = ()

    def field_keys(self) -> frozenset[str]:
        return frozenset(f.key for f in self.fields)

    def critical_keys(self) -> frozenset[str]:
        return frozenset(f.key for f in self.fields if f.critical)


PRIOR_AUTH_REQUEST = DocSchema(
    doc_type=DocType.PRIOR_AUTH_REQUEST,
    fields=(
        FieldSpec(key="member_id", label="Member ID", kind=FieldKind.MEMBER_ID, critical=True),
        FieldSpec(key="member_name", label="Member Name", kind=FieldKind.TEXT, critical=True),
        FieldSpec(key="member_dob", label="Date of Birth", kind=FieldKind.DATE, critical=True),
        FieldSpec(key="payer_name", label="Insurance / Payer", kind=FieldKind.TEXT),
        FieldSpec(key="plan_id", label="Plan / Group Number", kind=FieldKind.TEXT),
        FieldSpec(key="ordering_provider_name", label="Ordering Provider", kind=FieldKind.TEXT),
        FieldSpec(
            key="ordering_provider_npi", label="Provider NPI", kind=FieldKind.NPI, critical=True
        ),
        FieldSpec(
            key="servicing_facility",
            label="Servicing Facility",
            kind=FieldKind.TEXT,
            required=False,
        ),
        FieldSpec(
            key="diagnosis_code", label="Diagnosis (ICD-10)", kind=FieldKind.ICD10, critical=True
        ),
        FieldSpec(key="procedure_code", label="Procedure (CPT)", kind=FieldKind.CPT, critical=True),
        FieldSpec(
            key="date_of_service",
            label="Requested Date of Service",
            kind=FieldKind.DATE,
            critical=True,
        ),
        FieldSpec(
            key="urgency", label="Urgency (Standard/Urgent)", kind=FieldKind.TEXT, required=False
        ),
        FieldSpec(
            key="clinical_justification",
            label="Clinical Justification",
            kind=FieldKind.TEXT,
            required=False,
        ),
        FieldSpec(key="contact_phone", label="Contact Phone", kind=FieldKind.PHONE, required=False),
    ),
    tables=(
        TableSpec(
            key="requested_services",
            label="Requested Services",
            columns=("CPT", "Description", "Units"),
        ),
    ),
)

REFERRAL = DocSchema(
    doc_type=DocType.REFERRAL,
    fields=(
        FieldSpec(key="member_id", label="Member ID", kind=FieldKind.MEMBER_ID, critical=True),
        FieldSpec(key="member_name", label="Patient Name", kind=FieldKind.TEXT, critical=True),
        FieldSpec(key="member_dob", label="Date of Birth", kind=FieldKind.DATE, critical=True),
        FieldSpec(key="referring_provider_name", label="Referring Provider", kind=FieldKind.TEXT),
        FieldSpec(
            key="referring_provider_npi", label="Referring NPI", kind=FieldKind.NPI, critical=True
        ),
        FieldSpec(key="referred_to_provider", label="Referred To", kind=FieldKind.TEXT),
        FieldSpec(key="referred_to_specialty", label="Specialty", kind=FieldKind.TEXT),
        FieldSpec(
            key="diagnosis_code", label="Diagnosis (ICD-10)", kind=FieldKind.ICD10, critical=True
        ),
        FieldSpec(key="reason", label="Reason for Referral", kind=FieldKind.TEXT, required=False),
        FieldSpec(key="referral_date", label="Referral Date", kind=FieldKind.DATE),
    ),
)

EOB = DocSchema(
    doc_type=DocType.EOB,
    fields=(
        FieldSpec(key="member_id", label="Member ID", kind=FieldKind.MEMBER_ID, critical=True),
        FieldSpec(key="claim_number", label="Claim Number", kind=FieldKind.TEXT, critical=True),
        FieldSpec(key="payer_name", label="Payer", kind=FieldKind.TEXT),
        FieldSpec(key="provider_name", label="Provider", kind=FieldKind.TEXT),
        FieldSpec(key="statement_date", label="Statement Date", kind=FieldKind.DATE),
        FieldSpec(key="total_billed", label="Total Billed", kind=FieldKind.NUMBER, critical=True),
        FieldSpec(key="total_paid", label="Total Paid", kind=FieldKind.NUMBER, critical=True),
        FieldSpec(
            key="patient_responsibility", label="Patient Responsibility", kind=FieldKind.NUMBER
        ),
    ),
    tables=(
        TableSpec(
            key="claim_lines",
            label="Claim Lines",
            columns=("Date", "CPT", "Billed", "Allowed", "Paid", "Reason Code"),
            required=True,
        ),
    ),
)

LAB_REPORT = DocSchema(
    doc_type=DocType.LAB_REPORT,
    fields=(
        FieldSpec(key="member_name", label="Patient Name", kind=FieldKind.TEXT, critical=True),
        FieldSpec(key="member_dob", label="Date of Birth", kind=FieldKind.DATE, critical=True),
        FieldSpec(key="ordering_provider_name", label="Ordering Provider", kind=FieldKind.TEXT),
        FieldSpec(
            key="collection_date", label="Collection Date", kind=FieldKind.DATE, critical=True
        ),
        FieldSpec(key="lab_name", label="Laboratory", kind=FieldKind.TEXT, required=False),
    ),
    tables=(
        TableSpec(
            key="results",
            label="Results",
            columns=("Test", "Result", "Units", "Reference Range", "Flag"),
            required=True,
        ),
    ),
)

INSURANCE_CARD = DocSchema(
    doc_type=DocType.INSURANCE_CARD,
    fields=(
        FieldSpec(key="member_id", label="Member ID", kind=FieldKind.MEMBER_ID, critical=True),
        FieldSpec(key="member_name", label="Member Name", kind=FieldKind.TEXT, critical=True),
        FieldSpec(key="payer_name", label="Payer", kind=FieldKind.TEXT, critical=True),
        FieldSpec(key="plan_id", label="Group / Plan Number", kind=FieldKind.TEXT),
        FieldSpec(key="rx_bin", label="Rx BIN", kind=FieldKind.TEXT, required=False),
        FieldSpec(key="rx_pcn", label="Rx PCN", kind=FieldKind.TEXT, required=False),
        FieldSpec(
            key="customer_service_phone",
            label="Customer Service",
            kind=FieldKind.PHONE,
            required=False,
        ),
    ),
)

SCHEMA_REGISTRY: dict[DocType, DocSchema] = {
    s.doc_type: s for s in (PRIOR_AUTH_REQUEST, REFERRAL, EOB, LAB_REPORT, INSURANCE_CARD)
}
"""Registry consumed by extraction (CP15), validation (CP16), review UI (CP24), evals (CP26)."""
