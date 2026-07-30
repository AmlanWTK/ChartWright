# Local Development Platform (CP04-L)

Runs the full Chartwright backing stack on your machine with Docker Compose — the same technologies the production deployment uses (see ADR-0007 for the local-first decision and the mapping to cloud services).

## Prerequisites

- Docker Desktop (Windows/macOS) or Docker Engine + Compose v2 (Linux), running.
- ~4 GB free RAM for the stack.

## Start / stop

```bash
make local-up        # or: docker compose -f infra/local/docker-compose.yml up -d
make local-check     # smoke-check every service
make local-down      # stop, keep data
make local-nuke      # stop AND delete all data volumes
```

First start pulls images (~1–2 GB) and takes a few minutes; Temporal waits for Postgres and then initializes its schemas automatically.

## What's running

| Service | Endpoint | Credentials (dev-only) | Prod equivalent |
|---------|----------|------------------------|-----------------|
| Postgres 16 | `localhost:5432` (db `chartwright`) | `chartwright` / `chartwright_dev` | RDS |
| Kafka (KRaft) | `localhost:9092` | — | MSK |
| Temporal | `localhost:7233` | — | Temporal on EKS |
| Temporal Web UI | http://localhost:8233 | — | — |
| Redis 7 | `localhost:6379` | — | ElastiCache |
| MinIO (S3 API) | `localhost:9000` | `chartwright` / `chartwright_dev` | S3 |
| MinIO console | http://localhost:9001 | same | — |

A bucket named `chartwright-documents` is created automatically.

## Smoke check

```bash
make local-check     # or: uv run python scripts/check_local_stack.py
```

Verifies every service accepts connections and reports a per-service PASS/FAIL. Exit code 0 = all healthy (used as the CP04-L acceptance test).

## Notes & gotchas

- **Dev-only credentials, on localhost only.** Nothing here is reachable externally, and none of these secrets may ever be reused in a real environment.
- **Data persists** across `local-down`/`local-up` via named volumes; `local-nuke` wipes it.
- Kafka is a single-node KRaft broker with auto-topic-creation for convenience; production (MSK) will disable auto-create and use explicit topic management (CP10).
- If a port collides with something on your machine, override it in a `docker-compose.override.yml` (git-ignored).
- Windows: if Docker Desktop uses WSL2, first start after a reboot can be slow while the VM warms up.
