"""Gateway wiring from environment — the default assembly used by workers.

CHARTWRIGHT_OLLAMA_URL / CHARTWRIGHT_OLLAMA_MODEL select the local Tier-0 engine;
CHARTWRIGHT_GATEWAY_CACHE selects memory|redis. The frontier tier (2) currently chains
to the mock provider as a placeholder — the real API adapter slots in when a key is
configured (recorded in ADR-0008).
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from chartwright_gateway.cache import InMemoryCache, RedisCache, ResponseCache
from chartwright_gateway.gateway import ModelGateway
from chartwright_gateway.providers import MockProvider, ModelProvider, OllamaProvider


class GatewaySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CHARTWRIGHT_", extra="ignore")

    ollama_url: str = "http://localhost:11434"
    ollama_model: str = "moondream"
    gateway_cache: str = "memory"  # memory | redis
    redis_url: str = "redis://localhost:6379/0"


def build_default_gateway(settings: GatewaySettings | None = None) -> ModelGateway:
    s = settings or GatewaySettings()
    cache: ResponseCache = (
        RedisCache(s.redis_url) if s.gateway_cache == "redis" else InMemoryCache()
    )
    ollama: ModelProvider = OllamaProvider(base_url=s.ollama_url, model=s.ollama_model)
    fallback = MockProvider(name="fallback-mock", response="[unavailable: fallback response]")
    return ModelGateway(
        tier_chains={
            0: [ollama, fallback],  # local engine, mock as last resort
            1: [ollama, fallback],  # fine-tune slot (CP28) — same engine until then
            2: [fallback],  # frontier slot — real API adapter when a key exists
        },
        cache=cache,
    )
