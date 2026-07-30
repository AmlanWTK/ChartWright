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

## When to write an ADR

Write one when a decision is costly to reverse, affects multiple components, involves a non-obvious trade-off, or picks between competing technologies. Small, reversible choices don't need one.
