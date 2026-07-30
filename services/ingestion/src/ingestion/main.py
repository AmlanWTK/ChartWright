"""Ingestion API (CP09).

Endpoints:
- POST /v1/documents      multipart upload -> 202 {document_id, status, dedupe}
- GET  /v1/documents/{id} status lookup
- GET  /healthz, /readyz  probes (service-template pattern)

SECURITY NOTE (deliberate, temporary): tenant identity comes from the ``X-Tenant-Id``
header. This is a DEV-ONLY stand-in — real authentication (OIDC + server-side tenant
resolution, deferred CP07 per ADR-0007) replaces it before anything internet-facing.
The seam is this single dependency function; nothing else changes at swap time.
"""

from __future__ import annotations

import uuid
from functools import lru_cache
from typing import Annotated, Literal

from chartwright_db import DocumentRepository, build_engine, tenant_context
from fastapi import Depends, FastAPI, Header, HTTPException, UploadFile
from pydantic import BaseModel

from ingestion.config import Settings, get_settings
from ingestion.events import publisher_from_env
from ingestion.intake import IntakeService
from ingestion.scanner import EicarScanner
from ingestion.storage import ObjectStorage
from ingestion.validation import ValidationError

app = FastAPI(
    title="Chartwright — ingestion service",
    version="0.1.0",
    description="Document intake: validate, scan, dedupe, store, emit RECEIVED.",
)


@lru_cache(maxsize=1)
def _intake() -> IntakeService:
    settings: Settings = get_settings()
    return IntakeService(
        engine=build_engine(),
        storage=ObjectStorage(settings),
        scanner=EicarScanner(),
        # Transport by config: CHARTWRIGHT_EVENT_PUBLISHER=kafka wires the real pipeline.
        events=publisher_from_env(),
        settings=settings,
    )


def _tenant_id(x_tenant_id: Annotated[str, Header()]) -> uuid.UUID:
    """DEV-ONLY tenant resolution from a header — see module docstring."""
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="X-Tenant-Id must be a UUID") from exc


class SubmitResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    dedupe: bool
    file_type: str


class StatusResponse(BaseModel):
    document_id: uuid.UUID
    status: str
    doc_type: str | None
    page_count: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str


@app.post("/v1/documents", response_model=SubmitResponse, status_code=202)
async def submit_document(
    file: UploadFile,
    tenant_id: Annotated[uuid.UUID, Depends(_tenant_id)],
    external_ref: str | None = None,
) -> SubmitResponse:
    data = await file.read()
    try:
        result = _intake().submit(
            tenant_id=tenant_id,
            data=data,
            source_channel="api",
            external_ref=external_ref,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=422, detail={"code": exc.code, "message": exc.detail}
        ) from exc
    return SubmitResponse(
        document_id=result.document_id,
        status=result.status,
        dedupe=result.dedupe,
        file_type=result.file_type,
    )


@app.get("/v1/documents/{document_id}", response_model=StatusResponse)
def get_document(
    document_id: uuid.UUID,
    tenant_id: Annotated[uuid.UUID, Depends(_tenant_id)],
) -> StatusResponse:
    with tenant_context(_intake().engine, tenant_id) as session:
        doc = DocumentRepository(session, actor="ingestion-api").get(document_id)
        if doc is None:
            raise HTTPException(status_code=404, detail="Document not found")
        return StatusResponse(
            document_id=doc.id,
            status=doc.status,
            doc_type=doc.doc_type,
            page_count=doc.page_count,
        )


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok", service="ingestion")


@app.get("/readyz", response_model=HealthResponse)
def readyz() -> HealthResponse:
    # Real readiness (DB/storage checks) tightens when the service template lands (CP06).
    return HealthResponse(status="ok", service="ingestion")
