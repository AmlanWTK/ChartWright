"""Response cache: identical request + model → cached response (the cheapest inference).

Protocol + two implementations: in-memory (tests/dev) and Redis (shared across workers,
uses the CP04-L stack). Values are serialized ModelResponses with ``cached=True`` set on
the way out. TTL bounds staleness; cache keys are content hashes (see ModelRequest).
"""

from __future__ import annotations

from typing import Protocol

import redis

from chartwright_gateway.request import ModelResponse


class ResponseCache(Protocol):
    def get(self, key: str) -> ModelResponse | None: ...

    def set(self, key: str, response: ModelResponse) -> None: ...


class InMemoryCache:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, key: str) -> ModelResponse | None:
        raw = self._store.get(key)
        if raw is None:
            return None
        cached = ModelResponse.model_validate_json(raw)
        return cached.model_copy(update={"cached": True})

    def set(self, key: str, response: ModelResponse) -> None:
        self._store[key] = response.model_dump_json()


class RedisCache:
    def __init__(self, url: str = "redis://localhost:6379/0", ttl_seconds: int = 24 * 3600):
        self._client: redis.Redis = redis.Redis.from_url(url, decode_responses=True)
        self._ttl = ttl_seconds

    def get(self, key: str) -> ModelResponse | None:
        raw = self._client.get(key)
        if raw is None:
            return None
        cached = ModelResponse.model_validate_json(str(raw))
        return cached.model_copy(update={"cached": True})

    def set(self, key: str, response: ModelResponse) -> None:
        self._client.set(key, response.model_dump_json(), ex=self._ttl)
