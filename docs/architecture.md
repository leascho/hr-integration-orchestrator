# Architecture

## Style

The orchestrator is a **modular monolith** ([ADR-001](adr/001-modular-monolith.md)): one deployable unit with strict internal boundaries.

| Module | Responsibility | Depends on |
|---|---|---|
| `app/api` | HTTP contract, correlation ID, error envelopes, PII-free response models | orchestration, persistence |
| `app/domain` | Source contract, canonical model, mapping, error taxonomy, statuses | – (pure Python/Pydantic) |
| `app/orchestration` | Flow control, step tracking, retry policy, final-status decisions | domain, connectors (interfaces), persistence |
| `app/connectors` | HTTP adapters for downstream systems; error classification | domain |
| `app/persistence` | SQLAlchemy models and repository for the audit trail | domain (statuses) |
| `mock_services` | **Local-only** fake downstream systems with failure simulation | – (never imported by `app`) |

The orchestrator depends on connector **protocols** (`IdentityConnector`, `CollaborationConnector`, `NotificationConnector`), so tests and future implementations can swap adapters without touching the flow.

## System context

```mermaid
flowchart LR
    HR["Fictional HR Core Platform"] -- "employee.created (REST/JSON)" --> ORCH["HR Integration Orchestrator<br/>(FastAPI)"]
    ORCH -- "PUT /users/{person_id}" --> IDM["Identity Management System<br/>(fictional)"]
    ORCH -- "POST /tasks + Idempotency-Key" --> COLLAB["Collaboration Platform<br/>(fictional)"]
    ORCH -- "POST /notifications + Idempotency-Key" --> NOTIFY["Notification Service<br/>(fictional)"]
    ORCH -- "runs, steps, status history" --> DB[("PostgreSQL")]
    OPS["Operations / Support"] -- "GET /integration-runs" --> ORCH
```

## Component view

```mermaid
flowchart TB
    subgraph api [app/api]
        R[routes.py] --> D[dependencies.py]
    end
    subgraph orch [app/orchestration]
        O[EmployeeCreatedOrchestrator] --> RP[RetryPolicy]
    end
    subgraph domain [app/domain]
        SE[source_event] --> M[mapping] --> C[canonical]
        E[errors]
    end
    subgraph conn [app/connectors]
        B[HttpConnector] --> I[identity] & CO[collaboration] & N[notification]
    end
    subgraph pers [app/persistence]
        REP[IntegrationRunRepository] --> MOD[models]
    end
    R --> O
    O --> M
    O --> I & CO & N
    O --> REP
    B --> E
```

## End-to-end sequence

```mermaid
sequenceDiagram
    autonumber
    participant HR as HR Core (fictional)
    participant API as API layer
    participant ORC as Orchestrator
    participant DB as PostgreSQL
    participant IDM as Identity Mgmt
    participant COL as Collaboration
    participant NTF as Notification

    HR->>API: POST /api/v1/events/employee-created (X-Correlation-ID)
    API->>API: Schema validation (Pydantic)
    alt invalid payload
        API-->>HR: 422 VALIDATION_ERROR (no input echoed)
    end
    API->>ORC: process(event, correlation_id)
    ORC->>DB: INSERT run (RECEIVED) — unique event_id
    alt duplicate event_id
        ORC-->>API: existing run (duplicate=true)
        API-->>HR: 202 existing run id
    end
    ORC->>DB: status VALIDATED, IN_PROGRESS
    ORC->>ORC: map source → canonical
    ORC->>IDM: PUT /users/{person_id}
    IDM-->>ORC: 201/200 user_id
    ORC->>COL: POST /tasks (Idempotency-Key)
    COL-->>ORC: 201 task_id
    ORC->>NTF: POST /notifications (Idempotency-Key)
    NTF-->>ORC: 201 notification_id
    ORC->>DB: steps SUCCEEDED, run SUCCEEDED, history
    ORC-->>API: run
    API-->>HR: 202 {integration_run_id, correlation_id, status, received_at}
```

## Data model (audit)

```mermaid
erDiagram
    integration_runs ||--o{ integration_steps : has
    integration_runs ||--o{ integration_run_status_history : has
    integration_runs {
        string id PK
        string correlation_id
        string source_event_id UK
        string event_type
        string status
        string error_category
        string error_message
        int retry_count
        datetime received_at
        datetime started_at
        datetime finished_at
    }
    integration_steps {
        int id PK
        string run_id FK
        int sequence
        string step_name
        string status
        int attempts
        string error_category
        string error_message
        string external_reference
    }
    integration_run_status_history {
        int id PK
        string run_id FK
        string status
        string note
        datetime occurred_at
    }
```

No employee names, emails or other personal attributes are stored in these tables.

## Extension strategy for additional events

New lifecycle events (`employee.updated`, `employee.terminated`, `employee.cost_center_changed`) follow the same pattern:

1. **Contract**: add a Pydantic source model in `app/domain/source_event.py` (e.g. `EmployeeTerminatedEvent` with `event_type: Literal["employee.terminated"]`).
2. **Mapping**: reuse `CanonicalEmployee`; add partial/change models if the event carries deltas only.
3. **Steps**: declare a step list (e.g. `DEACTIVATE_IDENTITY`, `ARCHIVE_WORKSPACE`, `NOTIFY_MANAGER`).
4. **Connector methods**: extend the protocols (e.g. `IdentityConnector.deactivate_user`).
5. **Orchestrator**: add a dedicated orchestrator class, or refactor into a generic step-runner that receives a list of `(StepName, callable)`; the retry/step-tracking logic in `_execute` is already event-agnostic.
6. **Route**: either one route per event, or a single `POST /api/v1/events` with a discriminated union on `event_type`.
7. **Ordering**: for updates/terminations, compare `occurred_at` with the last processed event per `person_id` to reject stale events (out-of-order protection).

## Production evolution (not implemented)

- Accept event → persist → enqueue; process in a worker (see [ADR-003](adr/003-synchronous-demo-retries.md)).
- Transactional outbox for downstream calls; dead-letter queue feeding the manual-review process.
- Versioned DB migrations (Alembic) instead of `create_all`.
- OAuth2 client-credentials to downstream systems with secrets from a vault.

