# C4 Level 2 — Container View

Shows the major deployable/logical building blocks inside Chartwright and how they interact. Rationale for each is in the planning package (`08-system-architecture.md`, `13-backend-architecture.md`).

```mermaid
graph TB
    WEB["Web app (React/Next.js)<br/>review console + dashboards"]

    subgraph ControlPlane["Control plane (sync)"]
      GW["API Gateway / BFF<br/>authN/Z, rate limit"]
      ING["Ingestion service"]
      REVSVC["Review / HITL service"]
      ADMSVC["Admin / reporting"]
      AUTH["Identity (Keycloak/OIDC)"]
    end

    subgraph DataPlane["Async data plane"]
      TEMPORAL["Temporal<br/>durable workflow / state machine"]
      KAFKA["Kafka event log"]
      subgraph Workers["Stateless worker fleet"]
        W1["preprocess"]
        W2["classify"]
        W3["ocr / vlm (GPU)"]
        W4["extract"]
        W5["validate"]
        W6["policy / RAG"]
        W7["fhir-out"]
      end
    end

    subgraph AIEdge["AI edge"]
      MG["Model Gateway<br/>router + cache + meter + failover"]
      VLLM["Self-hosted VLMs (vLLM, GPU)"]
      FRONTIER["Frontier VLM APIs (BAA)"]
    end

    subgraph Stores["Data stores"]
      PG[("PostgreSQL<br/>state + audit, RLS")]
      S3[("S3 (KMS)<br/>PHI blobs")]
      QDRANT[("Qdrant<br/>policy embeddings")]
      REDIS[("Redis<br/>cache / idempotency")]
    end

    WEB --> GW
    GW --> ING
    GW --> REVSVC
    GW --> ADMSVC
    GW --> AUTH

    ING --> S3
    ING -->|RECEIVED event| TEMPORAL
    TEMPORAL <--> KAFKA
    KAFKA --> Workers
    W3 --> MG
    W4 --> MG
    W6 --> MG
    W6 --> QDRANT
    MG --> VLLM
    MG --> FRONTIER
    MG --> REDIS

    Workers --> PG
    REVSVC --> PG
    ADMSVC --> PG
    REVSVC <--> TEMPORAL
```

**Key seams:** a thin synchronous control plane; a fat async data plane (Temporal + Kafka + workers); a Model Gateway that abstracts/meters all model calls; polyglot stores with DB-enforced tenancy.
