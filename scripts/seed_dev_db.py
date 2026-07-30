"""Seed the local database with demo tenants and synthetic documents (CP08).

Uses the synthetic-data generator (CP03) so the seeded extractions are real grounded
data, not lorem ipsum. Idempotent: re-running adds nothing new for the same seed.

Usage:  uv run python scripts/seed_dev_db.py   (stack up + migrations applied first)
"""

from __future__ import annotations

import uuid

from chartwright_db import (
    DocumentRepository,
    ExtractionRepository,
    Tenant,
    admin_database_url,
    build_engine,
    no_tenant_session,
    tenant_context,
)
from chartwright_synthdata import generate_prior_auth
from sqlalchemy import select

TENANTS = [
    ("Lakeview Orthopedics (demo)", uuid.UUID("00000000-0000-0000-0000-00000000000a")),
    ("Summit Medical Group (demo)", uuid.UUID("00000000-0000-0000-0000-00000000000b")),
]
DOCS_PER_TENANT = 5


def ensure_tenants() -> None:
    admin = build_engine(admin_database_url())
    with no_tenant_session(admin) as s:
        for name, tid in TENANTS:
            if s.execute(select(Tenant).where(Tenant.id == tid)).scalar_one_or_none() is None:
                s.add(Tenant(id=tid, name=name))
                print(f"created tenant: {name}")


def seed_documents() -> None:
    app = build_engine()
    for t_index, (name, tid) in enumerate(TENANTS):
        with tenant_context(app, tid) as s:
            docs = DocumentRepository(s, actor="seed-script")
            exts = ExtractionRepository(s, actor="seed-script")
            for i in range(DOCS_PER_TENANT):
                doc_seed = 1000 * (t_index + 1) + i
                generated = generate_prior_auth(seed=doc_seed, document_id=f"seed_{doc_seed}")
                doc = docs.create_document(
                    source_channel="api",
                    content_hash=f"seedhash-{tid.hex[:8]}-{doc_seed}",
                    page_count=1,
                    external_ref=f"seed_{doc_seed}",
                )
                if doc.doc_type is not None:
                    continue  # already seeded on a previous run
                docs.transition_status(doc.id, "EXTRACTED")
                ext = exts.create_extraction(
                    document_id=doc.id,
                    doc_type=generated.labels.doc_type.value,
                    schema_version=generated.labels.schema_version,
                    overall_confidence=generated.labels.overall_confidence,
                )
                for f in generated.labels.fields:
                    exts.add_field(
                        extraction_id=ext.id,
                        field_key=f.key,
                        value_raw=f.value_raw,
                        confidence=f.confidence,
                        page_number=f.provenance.page,
                        bbox={
                            "x": f.provenance.bbox.x,
                            "y": f.provenance.bbox.y,
                            "w": f.provenance.bbox.w,
                            "h": f.provenance.bbox.h,
                        },
                        source_span=f.provenance.source_span,
                    )
                doc.doc_type = generated.labels.doc_type.value
                doc.doc_type_confidence = 1.0
        print(f"seeded {DOCS_PER_TENANT} documents for {name}")


def main() -> None:
    ensure_tenants()
    seed_documents()
    print("Seed complete.")


if __name__ == "__main__":
    main()
