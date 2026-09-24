# Security and Privacy

All data in this repository is fictional. The controls below are designed *as if* the data were real HR data, because that is the point of the exercise.

## Data classification

| Data | Classification | Where it exists |
|---|---|---|
| Names, work email, manager relation, location, cost center | Personal data (HR) | Request body in memory; sent to downstream systems that need it |
| `employee_id` / `person_id` | Pseudonymous identifier | Downstream calls, HTTP paths |
| `event_id`, `correlation_id`, run/step IDs, statuses | Operational metadata | Database, logs, API responses |

## Privacy-conscious logging

Decisions (implemented in `app/logging_config.py`):

1. **Raw payloads are never logged.** No log statement receives the event body or canonical model.
2. **Email addresses are masked** by a logging filter (`PiiMaskingFilter`) on every message, message argument and structured `extra` field. The filter acts as defense in depth for a future accidental log statement: `maya.klein@example.test` → `m***@example.test`.
3. **Only identifiers are logged**: `integration_run_id`, `event_id`, `correlation_id`, step name, error category, attempt, delay.
4. **Validation errors do not echo input.** FastAPI's default 422 response includes the submitted value. The custom handler returns only the field path and message.
5. **Exceptions are logged by type, not message**, because downstream exception messages can contain payload fragments.

Automated tests confirm that emails and names do not appear in application log records, and that status endpoints do not return PII.

## Data minimization

- The audit database stores **no personal attributes**, only identifiers, statuses and safe error messages.
- Each connector sends only the fields its system needs (see [data-mapping.md](data-mapping.md#downstream-projections)).
- Unknown source fields are rejected, so unexpected sensitive attributes cannot flow through.

## Input handling

- Strict Pydantic schema with patterns for IDs and codes; unknown fields are rejected.
- A caller-supplied `X-Correlation-ID` is accepted only if it matches `[A-Za-z0-9._-]{1,64}`; otherwise a UUID is generated. This prevents log injection.
- `event_id` is restricted to a safe character set.

## Secrets

- No secrets in the repository. `.env.example` contains only non-secret local defaults, and `.env` is git-ignored along with key and certificate file patterns.
- CI runs Gitleaks on every push and pull request.
- The container runs as a non-root user.

## Not implemented (production requirements)

| Control | Production approach |
|---|---|
| Inbound authentication | mTLS or OAuth2 (JWT with audience/scope checks) for the HR core caller; HMAC-signed webhooks as an alternative |
| Outbound authentication | OAuth2 client credentials per downstream system, with secrets from a vault |
| Transport security | TLS everywhere; the local Compose network is plain HTTP |
| Authorization for operations endpoints | Role-based access; the run endpoints are unauthenticated in the demo |
| Retention | Scheduled purge of run history (e.g. 90 days) aligned with retention policy |
| Encryption at rest | Managed database encryption |
| Rate limiting | API gateway |

