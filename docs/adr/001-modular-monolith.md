# ADR-001: Modular monolith

- **Status:** Accepted
- **Date:** 2026-09-24

## Context

The orchestrator coordinates one event type across three downstream systems. It needs clear boundaries (contract, mapping, connectors, persistence) so that it stays testable and can grow to more events. It must also run locally with a single `docker compose up`.

## Decision

Build a single deployable FastAPI service with strictly separated internal modules: `api`, `domain`, `orchestration`, `connectors` and `persistence`. The domain layer has no framework or I/O dependencies. The orchestrator depends on connector protocols, not concrete HTTP classes.

## Alternatives considered

- **Microservice per downstream system.** This adds network hops, deployment units and distributed failure modes without benefit at this scale.
- **Integration platform / iPaaS / BPMN engine.** This would hide the engineering concerns the project wants to show and add heavy infrastructure.

## Consequences

- Positive: simple local setup, fast tests, refactorable boundaries, and one audit database.
- Negative: all connectors scale together. A slow downstream system occupies orchestrator capacity (mitigated in production by a queue and workers, see ADR-003).
- A module can be extracted into its own service later if scaling or ownership requires it, because the boundaries already exist.

