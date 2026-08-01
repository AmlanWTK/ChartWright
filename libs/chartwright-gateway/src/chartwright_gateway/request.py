"""The gateway's request/response contract — every model call in the system uses this.

Providers are interchangeable behind this shape (ADR-0002): a worker asks for "a
completion for this prompt (+images) at this tier" and never knows which engine served
it. The response records provider/model/latency/cache status so cost attribution and
the router's tier-mix telemetry (CP17/CP32) fall out for free.
"""

from __future__ import annotations

import base64
import hashlib
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field


class ModelRequest(BaseModel):
    """One model invocation. ``images`` are raw bytes (page renders for OCR/vision)."""

    model_config = ConfigDict(frozen=True)

    prompt: str = Field(min_length=1)
    images: tuple[bytes, ...] = ()
    tier: Annotated[int, Field(ge=0, le=2)] = 0
    tenant_id: str = "unattributed"  # metering key; never used for authorization
    purpose: str = "general"  # ocr | classify | extract | ... (telemetry dimension)
    max_tokens: int = 1024
    temperature: float = 0.0  # deterministic by default (ADR-0005 discipline)

    def cache_key(self, model: str) -> str:
        """Content-hash key: identical request + model → identical cached response."""
        h = hashlib.sha256()
        h.update(model.encode())
        h.update(self.prompt.encode())
        for img in self.images:
            h.update(hashlib.sha256(img).digest())
        h.update(f"{self.max_tokens}|{self.temperature}".encode())
        return f"gw:{h.hexdigest()}"

    def images_b64(self) -> list[str]:
        return [base64.b64encode(i).decode() for i in self.images]


class ModelResponse(BaseModel):
    """The uniform result, whatever engine produced it."""

    text: str
    provider: str
    model: str
    tier: int
    latency_ms: float
    cached: bool = False
    tokens_in: int | None = None
    tokens_out: int | None = None


class AllProvidersFailedError(Exception):
    """Every provider in the tier's failover chain failed or was circuit-broken."""

    def __init__(self, tier: int, attempts: list[str]):
        self.tier = tier
        self.attempts = attempts
        super().__init__(f"tier {tier}: all providers failed ({', '.join(attempts)})")
