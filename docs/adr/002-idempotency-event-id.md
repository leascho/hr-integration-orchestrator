# ADR-002: Idempotency based on `event_id`

- **Status:** Accepted
- **Date:** 2026-09-24

## Context

Event sources and networks deliver messages **at least once**. The HR core may resend an event after a timeout, and an operator may resubmit manually. Duplicate processing must not create duplicate accounts, tasks or welcome emails.

## Decision

Use two layers of protection:

1. **Orchestrator level:** `integration_runs.source_event_id` has a **unique constraint**. When an event arrives, the orchestrator tries to create a run. If the `event_id` already exists (checked first, and enforced by the constraint under concurrency), the existing run is returned with `duplicate: true` and HTTP 202. No downstream calls are made.
2. **Downstream level:** every downstream call is idempotent on its own:
   - Identity: `PUT /users/{person_id}` (upsert keyed by a stable business key),
   - Collaboration and Notification: `Idempotency-Key: {event_id}:{step_name}` header.

## Consequences

- Duplicate submissions are cheap and safe. Tests prove that three submissions produce one user, one task and one notification.
- A new event for the same employee (new `event_id`) updates the identity instead of creating a duplicate.
- The duplicate response returns the *original* run status, which may still be a failure. Callers must not treat 202 as success. They should read `status`.
- Replaying a failed run requires a new mechanism (a replay endpoint) instead of resubmitting the same event. This is intentional, because it keeps replays auditable.
- Payload changes under the same `event_id` are ignored. A production system might store a payload hash and reject such conflicts with 409.

