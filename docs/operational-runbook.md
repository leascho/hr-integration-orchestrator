# Operational Runbook

Audience: integration support engineers operating the (fictional) orchestrator.

## Health

```bash
curl -s http://localhost:8000/health
# {"status":"ok","database":"ok"}   -> 503 if the database is unreachable
```

## Find runs needing attention

```bash
curl -s "http://localhost:8000/api/v1/integration-runs?status=MANUAL_REVIEW_REQUIRED"
curl -s "http://localhost:8000/api/v1/integration-runs?status=FAILED"
curl -s "http://localhost:8000/api/v1/integration-runs?status=RETRYING"   # should be empty in the synchronous demo
```

## Inspect a run

```bash
curl -s http://localhost:8000/api/v1/integration-runs/<integration_run_id>
```

Check the following:
- `error_category` and `error_message` at run level,
- the first step with `status = FAILED` and its `attempts`,
- `status_history` for the timeline, including retry notes.

Use `correlation_id` to search logs across systems:

```bash
docker compose logs orchestrator | grep '"correlation_id": "<id>"'
```

## Triage by category

| Category | Likely cause | Action |
|---|---|---|
| `VALIDATION_ERROR` / `BUSINESS_RULE_ERROR` (run `FAILED`) | Bad source data | Ask the HR data owner to correct the record; the source emits a **new** event with a new `event_id` |
| `AUTHENTICATION_ERROR` | Expired or rotated downstream credentials | Fix the credential configuration, then replay |
| `TRANSIENT_TECHNICAL_ERROR` (exhausted) | Prolonged downstream outage or throttling | Confirm the downstream system has recovered, then replay |
| `DEPENDENCY_UNAVAILABLE` | Wrong base URL, DNS or network issue, service down | Check the `*_SERVICE_BASE_URL` configuration and connectivity |
| `PERMANENT_TECHNICAL_ERROR` | Downstream bug or contract change | Escalate to the downstream owner with the `correlation_id` |

## Replay

**Current demo:** re-submitting the same `event_id` returns the existing run (`duplicate: true`) by design. To reprocess locally, reset the environment (`make reset`), or submit the event with a new `event_id` after the root cause is fixed. This is safe because Identity uses an upsert and the other systems deduplicate by idempotency key.

**Production design:** a `POST /api/v1/integration-runs/{id}/replay` endpoint (restricted to operators) would resume from the first non-succeeded step, keeping the same run ID and appending to the history.

## Demo failure simulation

The mock downstream service reads these variables at startup:

| Variable | Effect |
|---|---|
| `SIMULATE_IDENTITY_TIMEOUT=true` | Identity returns HTTP 504 for the first `SIMULATE_IDENTITY_TIMEOUT_FAILURES` (default 2) attempts per person |
| `SIMULATE_COLLABORATION_FAILURE=true` | Collaboration always returns HTTP 500 |
| `SIMULATE_NOTIFICATION_FAILURE=true` | Notification always returns HTTP 503 |

To change them at runtime without a restart:

```bash
curl -s -X PUT http://localhost:8100/_simulation -H "Content-Type: application/json" \
  -d '{"identity_timeout": true, "identity_timeout_failures": 2, "collaboration_failure": false, "notification_failure": false}'
curl -s http://localhost:8100/_stats   # counts of users/tasks/notifications in the mock
```

## Common issues

| Symptom | Resolution |
|---|---|
| `orchestrator` exits at startup | Postgres not ready or `DATABASE_URL` is wrong; run `docker compose logs postgres` |
| All runs end with `DEPENDENCY_UNAVAILABLE` | `mock-downstream` is not running or the base URLs are wrong |
| Port 5432/8000/8100 already in use | Stop the conflicting service or change the host port in `docker-compose.yml` |

