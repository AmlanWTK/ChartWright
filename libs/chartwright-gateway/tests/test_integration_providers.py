"""Integration tests: live Ollama (local model) and Redis cache (CP04-L stack).

Each skips cleanly if its dependency isn't running, with instructions in the skip
message — so `pytest -m integration` stays honest about what was actually proven.
"""

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


class TestOllamaLive:
    def test_generate_text_via_local_model(self) -> None:
        settings = GatewaySettings()
        if not _ollama_ready(settings):
            pytest.skip(
                f"Ollama not ready (install: winget install Ollama.Ollama; "
                f"then: ollama pull {settings.ollama_model})"
            )
        gw = ModelGateway(
            {0: [OllamaProvider(base_url=settings.ollama_url, model=settings.ollama_model)]}
        )
        result = gw.generate(
            ModelRequest(prompt="Reply with exactly the word: PONG", tenant_id="itest")
        )
        assert result.text.strip() != ""
        assert result.provider.startswith("ollama:")
        assert result.latency_ms > 0
        # And the cache makes the second call effectively free:
        again = gw.generate(
            ModelRequest(prompt="Reply with exactly the word: PONG", tenant_id="itest")
        )
        assert again.cached is True


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
