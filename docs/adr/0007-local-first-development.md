# ADR-0007: Local-first development platform; cloud provisioning deferred

- **Status:** Accepted
- **Date:** 2026-07-30
- **Deciders:** Project owner
- **Checkpoint:** CP04-L (replaces CP04's original sequencing)
- **Reversibility:** Two-way door (cloud checkpoints remain in the roadmap, just resequenced)

## Context

The original roadmap provisioned AWS infrastructure at CP04 (Terraform: VPC, EKS, RDS, S3, KMS), before any application services exist. That front-loads real monthly cost (~$50–150 for a dev environment, EKS being the largest item) during a phase where every consumer of that infrastructure is still local code. This is a solo, self-funded build; burn rate matters.

## Options considered

### Option A — Provision AWS now (original CP04)
- Pros: Production-realistic from day one; IaC exercised early; strongest infra signal.
- Cons: Pays for idle infrastructure for weeks; slower iteration (every change round-trips to the cloud); cloud debugging friction while the basics are still being built.

### Option B — Local-first: Docker Compose platform now, Terraform/EKS when needed
- Pros: Zero cost; seconds-fast iteration; the local stack uses the **same engines** (Postgres 16, Kafka, Temporal, Redis) so application code is written once; MinIO's S3-compatible API means the object-storage code path only changes an endpoint. Cloud checkpoints (Terraform, EKS, GitOps, observability stack) remain intact and move later — they are *deferred, not deleted*.
- Cons: Some cloud-specific behavior (IAM, KMS, networking, managed-service quirks) surfaces later; the walking-skeleton milestone is proven locally first.

### Option C — Minimal AWS free-tier (VPC + RDS + S3 only)
- Pros: Real IaC early at near-zero cost.
- Cons: Splits effort across two environments while still lacking the expensive parts (EKS/GPU) that motivated cloud in the first place; worst of both.

## Decision

Adopt **Option B**. CP04 becomes **CP04-L: Local Development Platform** — a Docker Compose stack (Postgres 16, single-node KRaft Kafka, Temporal + UI, Redis 7, MinIO with an auto-created bucket) with health checks, a dependency-free smoke-check script, and Make targets. The original cloud checkpoints (Terraform/environments, EKS/GitOps, and the managed observability rollout) are resequenced to just before the first checkpoint that genuinely needs cloud capacity (GPU serving at CP12, or earlier if a pilot demands it).

**Guardrail against drift:** all application code must depend on *interfaces/endpoints*, never on "it's local" assumptions — connection strings and S3 endpoints come from configuration, so the swap to RDS/MSK/S3 is config, not code. This is checked at review time from CP08 onward.

## Consequences

- **Positive:** $0 infrastructure cost during the build-heavy phase; much faster feedback loops; the checkpoint cadence (CP08 data layer next) proceeds immediately.
- **Negative / trade-offs:** Cloud-specific hardening (IAM, KMS, NetworkPolicies, Karpenter/KEDA) is validated later than originally planned; DR/scale checkpoints (CP30+) still require the cloud environment to exist by then.
- **Follow-ups:** Re-insert the cloud checkpoints (as CP-Cloud-1: Terraform/envs, CP-Cloud-2: EKS/GitOps) no later than immediately before CP12 GPU serving; revisit this ADR at that point.

## Links

- Replaces sequencing of: CP04 (IaC), CP05 (K8s/GitOps), parts of CP06 (managed observability) · `infra/local/` · ADR-0001, ADR-0004
