"""Unit tests: every gateway mechanism proven deterministically (no live services).

Covers: caching (hit + metering of hits), failover chains, circuit breaker open/close,
per-tenant metering, cache-key content sensitivity, and error surfacing.
"""

import pytest

from chartwright_gateway import (
    AllProvidersFailedError,
    CircuitBreaker,
    InMemoryCache,
    Meter,
    MockProvider,
    ModelGateway,
    ModelRequest,
)


def _req(prompt: str = "hello", tenant: str = "t1", tier: int = 0) -> ModelRequest:
    return ModelRequest(prompt=prompt, tenant_id=tenant, tier=tier)


class TestCaching:
    def test_second_identical_call_is_served_from_cache(self) -> None:
        provider = MockProvider()
        gw = ModelGateway({0: [provider]})
        first = gw.generate(_req())
        second = gw.generate(_req())
        assert first.cached is False
        assert second.cached is True
        assert provider.calls == 1  # the engine was only hit once

    def test_different_prompts_do_not_share_cache(self) -> None:
        provider = MockProvider()
        gw = ModelGateway({0: [provider]})
        gw.generate(_req("prompt A"))
        gw.generate(_req("prompt B"))
        assert provider.calls == 2

    def test_different_images_do_not_share_cache(self) -> None:
        provider = MockProvider()
        gw = ModelGateway({0: [provider]})
        gw.generate(ModelRequest(prompt="p", images=(b"page-1",)))
        gw.generate(ModelRequest(prompt="p", images=(b"page-2",)))
        assert provider.calls == 2

    def test_cache_hits_are_metered(self) -> None:
        gw = ModelGateway({0: [MockProvider()]})
        gw.generate(_req(tenant="acme"))
        gw.generate(_req(tenant="acme"))
        usage = gw.meter.usage("acme")
        assert usage.calls == 2
        assert usage.cache_hits == 1


class TestFailover:
    def test_failing_primary_falls_over_to_secondary(self) -> None:
        bad = MockProvider(name="bad", fail=True)
        good = MockProvider(name="good", response="SERVED_BY_GOOD")
        gw = ModelGateway({0: [bad, good]})
        result = gw.generate(_req())
        assert result.provider == "good"
        assert result.text == "SERVED_BY_GOOD"

    def test_all_providers_failing_raises_with_attempt_trail(self) -> None:
        gw = ModelGateway({0: [MockProvider(name="a", fail=True), MockProvider(name="b", fail=True)]})
        with pytest.raises(AllProvidersFailedError) as exc:
            gw.generate(_req())
        assert exc.value.attempts == ["a(failed)", "b(failed)"]

    def test_unconfigured_tier_is_an_error(self) -> None:
        gw = ModelGateway({0: [MockProvider()]})
        with pytest.raises(ValueError, match="tier 2"):
            gw.generate(_req(tier=2))


class TestCircuitBreaker:
    def test_opens_after_threshold_and_router_skips_it(self) -> None:
        bad = MockProvider(name="bad", fail=True)
        good = MockProvider(name="good")
        breaker = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
        gw = ModelGateway({0: [bad, good]}, breaker=breaker)

        gw.generate(_req("p1"))  # bad fails (1)
        gw.generate(_req("p2"))  # bad fails (2) -> circuit opens
        assert breaker.is_open("bad")

        bad.calls = 0
        gw.generate(_req("p3"))  # bad skipped entirely
        assert bad.calls == 0

    def test_success_closes_the_circuit(self) -> None:
        breaker = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.0)  # immediate half-open
        flaky = MockProvider(name="flaky", fail=True)
        gw = ModelGateway({0: [flaky, MockProvider(name="backup")]}, breaker=breaker)
        gw.generate(_req("p1"))  # flaky fails -> opens (cooldown 0 -> half-open next call)
        flaky._fail = False  # provider recovers
        gw.generate(_req("p2"))  # probe succeeds
        assert not breaker.is_open("flaky")


class TestMetering:
    def test_usage_accumulates_per_tenant_and_provider(self) -> None:
        gw = ModelGateway({0: [MockProvider(name="engine")]})
        gw.generate(_req("a", tenant="t-a"))
        gw.generate(_req("b", tenant="t-a"))
        gw.generate(_req("c", tenant="t-b"))
        assert gw.meter.usage("t-a").calls == 2
        assert gw.meter.usage("t-b").calls == 1
        assert gw.meter.usage("t-a").by_provider["engine"] == 2

    def test_meter_records_tokens(self) -> None:
        gw = ModelGateway({0: [MockProvider()]})
        gw.generate(_req("one two three", tenant="t"))
        assert gw.meter.usage("t").tokens_in == 3


class TestCacheImplementations:
    def test_in_memory_roundtrip_marks_cached(self) -> None:
        from chartwright_gateway import ModelResponse

        cache = InMemoryCache()
        resp = ModelResponse(text="x", provider="p", model="m", tier=0, latency_ms=1.0)
        cache.set("k", resp)
        got = cache.get("k")
        assert got is not None and got.cached is True

    def test_miss_returns_none(self) -> None:
        assert InMemoryCache().get("absent") is None
