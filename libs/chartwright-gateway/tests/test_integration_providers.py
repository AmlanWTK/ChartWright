"""Integration tests: live Ollama (local model) and Redis cache (CP04-L stack).

Each skips cleanly if its dependency isn't running, with instructions in the skip
message — so `pytest -m integration` stays honest about what was actually proven.
"""

import base64
import uuid

import httpx
import pytest
from chartwright_gateway import (
    GatewaySettings,
    ModelGateway,
    ModelRequest,
    ModelResponse,
    OllamaProvider,
    RedisCache,
)

pytestmark = pytest.mark.integration


def _ollama_ready(settings: GatewaySettings) -> bool:
    try:
        resp = httpx.get(f"{settings.ollama_url}/api/tags", timeout=3.0)
        resp.raise_for_status()
    except httpx.HTTPError:
        return False
    models = [m.get("name", "") for m in resp.json().get("models", [])]
    return any(settings.ollama_model in name for name in models)


# A 128x128 PNG: a black square on white. Embedded as a literal so this test needs no
# imaging library -- chartwright-gateway deliberately depends on none, taking raw bytes.
_TEST_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAIAAAACACAAAAADmVT4XAAAAbUlEQVR42u3bMQoAMAgDQC39"
    "/5ftC7oJFnpZHXLgnKyYzQoAAAAAAAAAAAAAgOHs2yGbi8oLAAAAAAAAAAAAAAAAAAAAAAAA"
    "AAAAAAAAAAAAAAAAAAAAAAAAAABeBaSdEQAAAAAAAAAAAMD3gAMvYQP/J9C/LgAAAABJRU5E"
    "rkJggg=="
)


class TestOllamaLive:
    def test_generate_via_local_model(self) -> None:
        """The Tier-0 adapter round-trips against a live Ollama server.

        Sends an image, because the default Tier-0 model (moondream) is vision-only:
        given a text-only prompt it emits end-of-sequence immediately and returns an
        empty string (observed during CP14 verification -- eval_count=1). That is
        correct behavior for the model, not a fault in the adapter, so a text-only
        prompt proves nothing here. This test previously asserted non-empty text from
        a text-only prompt and had never actually run: Ollama was not installed until
        CP14, so it skipped silently through the whole of CP11.
        """
        settings = GatewaySettings()
        if not _ollama_ready(settings):
            pytest.skip(
                f"Ollama not ready (install: winget install Ollama.Ollama; "
                f"then: ollama pull {settings.ollama_model})"
            )
        gw = ModelGateway(
            {0: [OllamaProvider(base_url=settings.ollama_url, model=settings.ollama_model)]}
        )
        request = ModelRequest(
            prompt="Describe this image.", images=(_TEST_PNG,), tenant_id="itest"
        )
        result = gw.generate(request)
        assert result.provider.startswith("ollama:")
        assert result.latency_ms > 0
        # tokens_in > 0 proves the server actually evaluated our prompt + image, which
        # a broken adapter (or a silently-dropped image) could not fake.
        assert result.tokens_in is not None and result.tokens_in > 0
        assert result.text.strip() != ""
        # And the cache makes the second call effectively free:
        assert gw.generate(request).cached is True


class TestRedisCacheLive:
    def test_roundtrip_against_local_stack(self) -> None:
        cache = RedisCache("redis://localhost:6379/0", ttl_seconds=60)
        try:
            key = f"gw:test:{uuid.uuid4().hex}"
            resp = ModelResponse(text="hello", provider="p", model="m", tier=0, latency_ms=1.0)
            cache.set(key, resp)
        except Exception:  # pragma: no cover
            pytest.skip("Redis not reachable (make local-up)")
        got = cache.get(key)
        assert got is not None
        assert got.text == "hello"
        assert got.cached is True
