"""Circuit breaker + per-tenant metering — the gateway's operational half.

Breaker: after N consecutive failures a provider is 'open' (skipped by the router) for a
cooldown window, so a dead engine doesn't absorb every request's timeout budget. A single
success closes it.

Metering: every call is counted per tenant/provider/purpose (calls, tokens, latency).
This is the raw feed for cost dashboards and per-tenant quotas (CP25/CP32). In-memory
here; a Redis-backed aggregate lands when the dashboard consumes it — the interface is
what matters now.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field

from chartwright_gateway.request import ModelResponse

logger = logging.getLogger("chartwright.gateway")


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 3, cooldown_seconds: float = 30.0):
        self._threshold = failure_threshold
        self._cooldown = cooldown_seconds
        self._failures: dict[str, int] = defaultdict(int)
        self._opened_at: dict[str, float] = {}

    def is_open(self, provider: str) -> bool:
        opened = self._opened_at.get(provider)
        if opened is None:
            return False
        if time.monotonic() - opened >= self._cooldown:
            # Half-open: allow a probe attempt; a success will close it.
            return False
        return True

    def record_failure(self, provider: str) -> None:
        self._failures[provider] += 1
        if self._failures[provider] >= self._threshold:
            if provider not in self._opened_at:
                logger.warning("circuit OPEN for provider %s", provider)
            self._opened_at[provider] = time.monotonic()

    def record_success(self, provider: str) -> None:
        self._failures[provider] = 0
        if self._opened_at.pop(provider, None) is not None:
            logger.info("circuit CLOSED for provider %s", provider)


@dataclass
class TenantUsage:
    calls: int = 0
    cache_hits: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms_total: float = 0.0
    by_provider: dict[str, int] = field(default_factory=dict)


class Meter:
    """Per-tenant usage accounting. No PHI — counts and identifiers only."""

    def __init__(self) -> None:
        self._usage: dict[str, TenantUsage] = defaultdict(TenantUsage)

    def record(self, tenant_id: str, response: ModelResponse) -> None:
        u = self._usage[tenant_id]
        u.calls += 1
        if response.cached:
            u.cache_hits += 1
        u.tokens_in += response.tokens_in or 0
        u.tokens_out += response.tokens_out or 0
        u.latency_ms_total += response.latency_ms
        u.by_provider[response.provider] = u.by_provider.get(response.provider, 0) + 1
        logger.info(
            "meter tenant=%s provider=%s cached=%s latency_ms=%.1f",
            tenant_id,
            response.provider,
            response.cached,
            response.latency_ms,
        )

    def usage(self, tenant_id: str) -> TenantUsage:
        return self._usage[tenant_id]
