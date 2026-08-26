"""Model providers: the protocol + Ollama (local Tier-0) and Mock (tests/failover).

Adding a provider = one class implementing ``ModelProvider``. Nothing else in the
system changes — that is the portability guarantee of ADR-0002. The frontier-API
adapter (Anthropic/OpenAI/Google) slots in here when a key is available.
"""

from __future__ import annotations

import time
from typing import Protocol

import httpx

from chartwright_gateway.request import ModelRequest, ModelResponse


class ProviderError(Exception):
    """A provider failed to serve a request (drives failover + circuit breaker)."""


class ModelProvider(Protocol):
    name: str

    def generate(self, request: ModelRequest) -> ModelResponse: ...


class OllamaProvider:
    """Local Ollama server (default http://localhost:11434) — the Tier-0 stand-in.

    Serves small vision-capable models (moondream, llava, qwen-vl family) on CPU/GPU
    with zero marginal cost. Production Tier-0 swaps this for vLLM-served dots.ocr /
    Qwen3-VL behind the same protocol (config change + one adapter, per ADR-0007's
    guardrail).
    """

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "moondream"):
        self.name = f"ollama:{model}"
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._client = httpx.Client(timeout=httpx.Timeout(120.0, connect=5.0))

    def generate(self, request: ModelRequest) -> ModelResponse:
        payload: dict[str, object] = {
            "model": self._model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
                # Observed in practice (CP14): small local VLMs (moondream) can degrade
                # into a repeated-token loop under greedy decoding (temperature=0) with
                # no penalty, burning the full token budget on garbage. A mild penalty
                # is cheap insurance and does not affect determinism in any way ADR-0005
                # cares about (same input still produces the same output).
                "repeat_penalty": 1.1,
            },
        }
        if request.images:
            payload["images"] = request.images_b64()
        if request.response_format is not None:
            # Ollama's structured-output mode: constrains decoding to a JSON Schema
            # grammar instead of relying on the model to freehand a parseable format.
            payload["format"] = request.response_format

        started = time.perf_counter()
        try:
            resp = self._client.post(f"{self._base_url}/api/generate", json=payload)
            resp.raise_for_status()
        except httpx.HTTPError as exc:
            msg = f"{self.name}: {exc}"
            raise ProviderError(msg) from exc
        latency_ms = (time.perf_counter() - started) * 1000

        body = resp.json()
        return ModelResponse(
            text=str(body.get("response", "")),
            provider=self.name,
            model=self._model,
            tier=request.tier,
            latency_ms=latency_ms,
            tokens_in=body.get("prompt_eval_count"),
            tokens_out=body.get("eval_count"),
        )


class MockProvider:
    """Deterministic provider for tests and as a last-resort failover target.

    Echoes a scripted response; optionally fails on demand to exercise the breaker
    and failover paths deterministically.
    """

    def __init__(self, name: str = "mock", *, response: str = "MOCK_RESPONSE", fail: bool = False):
        self.name = name
        self._response = response
        self._fail = fail
        self.calls = 0

    def generate(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if self._fail:
            msg = f"{self.name}: simulated failure"
            raise ProviderError(msg)
        return ModelResponse(
            text=self._response,
            provider=self.name,
            model="mock-1",
            tier=request.tier,
            latency_ms=0.1,
            tokens_in=len(request.prompt.split()),
            tokens_out=len(self._response.split()),
        )
