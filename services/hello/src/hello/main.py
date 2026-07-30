"""Minimal FastAPI application with health and readiness endpoints.

The health/readiness split mirrors what Kubernetes will probe (liveness vs. readiness)
once we deploy real services in later checkpoints. Keeping the pattern here means the
service template and CI lane are proven before any business logic exists.
"""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI(
    title="Chartwright — hello service",
    version="0.1.0",
    description="Reference service proving the CI lane. No PHI, no business logic.",
)


class HealthResponse(BaseModel):
    """Response body for the health/readiness probes."""

    status: Literal["ok"]
    service: str
    version: str


def _payload() -> HealthResponse:
    return HealthResponse(status="ok", service="hello", version=app.version)


@app.get("/healthz", response_model=HealthResponse, tags=["health"])
def healthz() -> HealthResponse:
    """Liveness probe: the process is up and can serve requests."""
    return _payload()


@app.get("/readyz", response_model=HealthResponse, tags=["health"])
def readyz() -> HealthResponse:
    """Readiness probe: the service is ready to receive traffic.

    Real services will additionally check downstream dependencies (DB, broker) here.
    """
    return _payload()


@app.get("/", tags=["root"])
def root() -> dict[str, str]:
    """Human-friendly root pointer."""
    return {"message": "Chartwright hello service. See /healthz and /docs."}
