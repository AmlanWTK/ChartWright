# chartwright-gateway (CP11)

The **single choke point for every model call** (ADR-0002/0008): tier-based provider
routing with failover, content-hash response caching, circuit breaking, and per-tenant
metering. Workers never talk to a model engine directly — they call
`ModelGateway.generate()` and the gateway decides who serves it.

```python
from chartwright_gateway import ModelRequest, build_default_gateway

gw = build_default_gateway()  # Ollama Tier-0/1, mock frontier slot, memory/redis cache
resp = gw.generate(ModelRequest(prompt="...", images=(page_png,), tier=0, tenant_id=t))
print(resp.text, resp.provider, resp.latency_ms, resp.cached)
```

## Mechanisms (all unit-tested without live services)

| Mechanism | Behavior |
|-----------|----------|
| **Routing** | Per-tier ordered provider chains; first healthy provider serves |
| **Cache** | sha256(content) → response; identical request never hits an engine twice |
| **Circuit breaker** | N consecutive failures → provider skipped for a cooldown; success closes |
| **Failover** | Failed/open providers are skipped down the chain; exhausted chain raises with an attempt trail |
| **Metering** | Per-tenant calls / cache hits / tokens / latency / provider mix — the CP25/CP32 dashboard feed |

## Local engine: Ollama

```powershell
winget install Ollama.Ollama     # or https://ollama.com/download
ollama pull moondream            # small vision model, CPU-friendly (~1.7GB)
# optional larger: ollama pull llava   (set CHARTWRIGHT_OLLAMA_MODEL=llava)
```

Config (env): `CHARTWRIGHT_OLLAMA_URL` (default `http://localhost:11434`),
`CHARTWRIGHT_OLLAMA_MODEL` (default `moondream`), `CHARTWRIGHT_GATEWAY_CACHE`
(`memory`|`redis`), `CHARTWRIGHT_REDIS_URL`.

## Honest scope notes (ADR-0008)

- In-process library, not a network service — the HTTP facade arrives with a second
  consumer or cloud re-entry.
- Tier 2 chains to a labeled mock until a frontier API key is configured; adding the
  real adapter is one `ModelProvider` class.
- Ollama accuracy ≠ production accuracy: CP11–CP15 prove mechanisms; binding accuracy
  numbers come from the eval harness (CP26) on production-grade engines.
