"""The Model Gateway: route → cache → breaker-guarded provider chain → meter.

The single choke point of ADR-0002. Per tier there is an ordered failover chain of
providers; the first healthy one serves the request. The flow per call:

    1. cache lookup (content hash)          — free is the cheapest inference
    2. walk the tier's chain, skipping open circuits
    3. on success: meter + cache + return
    4. on failure: record on breaker, try next provider
    5. chain exhausted: AllProvidersFailedError (caller's retry/DLQ handles it)

Escalation policy (which tier a request *should* use) is CP17's concern; this class is
the mechanism it will drive.
"""

from __future__ import annotations

import logging

from chartwright_gateway.cache import InMemoryCache, ResponseCache
from chartwright_gateway.providers import ModelProvider, ProviderError
from chartwright_gateway.request import AllProvidersFailedError, ModelRequest, ModelResponse
from chartwright_gateway.resilience import CircuitBreaker, Meter

logger = logging.getLogger("chartwright.gateway")


class ModelGateway:
    def __init__(
        self,
        tier_chains: dict[int, list[ModelProvider]],
        *,
        cache: ResponseCache | None = None,
        breaker: CircuitBreaker | None = None,
        meter: Meter | None = None,
    ):
        if not tier_chains:
            msg = "at least one tier chain is required"
            raise ValueError(msg)
        self._chains = tier_chains
        self._cache = cache or InMemoryCache()
        self._breaker = breaker or CircuitBreaker()
        self.meter = meter or Meter()

    def generate(self, request: ModelRequest) -> ModelResponse:
        chain = self._chains.get(request.tier)
        if not chain:
            msg = f"no provider chain configured for tier {request.tier}"
            raise ValueError(msg)

        # 1) Cache — keyed on the chain's primary model identity.
        primary = chain[0]
        key = request.cache_key(primary.name)
        cached = self._cache.get(key)
        if cached is not None:
            self.meter.record(request.tenant_id, cached)
            return cached

        # 2-4) Failover chain with circuit breaking.
        attempts: list[str] = []
        for provider in chain:
            if self._breaker.is_open(provider.name):
                attempts.append(f"{provider.name}(open)")
                continue
            try:
                response = provider.generate(request)
            except ProviderError as exc:
                logger.warning("provider failed, trying next: %s", exc)
                self._breaker.record_failure(provider.name)
                attempts.append(f"{provider.name}(failed)")
                continue
            self._breaker.record_success(provider.name)
            self.meter.record(request.tenant_id, response)
            self._cache.set(key, response)
            return response

        # 5) Nothing served it.
        raise AllProvidersFailedError(request.tier, attempts)
