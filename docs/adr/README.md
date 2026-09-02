# Architecture Decision Records (ADRs)

ADRs capture significant architectural decisions with their context, options, and consequences. Use the [template](0000-adr-template.md) for new ones. Numbering is sequential; superseded ADRs are marked, not deleted.

## Index

| ADR | Decision | Status |
|-----|----------|--------|
| [0001](0001-async-event-driven-pipeline.md) | Async, event-driven processing pipeline | Accepted |
| [0002](0002-model-gateway-router.md) | Cost-aware Model Gateway with routing cascade | Accepted |
| [0003](0003-grounding-contract.md) | Mandatory grounding contract (bbox + span + confidence) | Accepted |
| [0004](0004-postgres-kafka-temporal.md) | Postgres + Kafka + Temporal | Accepted |
| [0005](0005-bounded-agent.md) | Bounded, tool-limited agent | Accepted |
| [0006](0006-eval-as-ci-gate.md) | Evaluation harness as a CI gate | Accepted |
| [0007](0007-local-first-development.md) | Local-first development platform; cloud deferred | Accepted |
| [0008](0008-gateway-library-ollama.md) | Gateway as in-process library; Ollama as local Tier-0 | Accepted |
| [0009](0009-shared-object-storage-library.md) | Shared object-storage library | Accepted |
| [0010](0010-describe-then-map-classification.md) | Classify by describe-then-map, not constrained selection | Accepted |
| [0011](0011-deterministic-label-anchored-extraction.md) | Extraction's cheapest tier uses no model at all | Accepted |
| [0012](0012-packet-fanout-parent-joins-children.md) | A fanned-out upload completes when its packets complete | Accepted |
| [0013](0013-read-only-console-ahead-of-cp16.md) | A read-only console comes before CP16 | Accepted |

## When to write an ADR

Write one when a decision is costly to reverse, affects multiple components, involves a non-obvious trade-off, or picks between competing technologies. Small, reversible choices don't need one.
