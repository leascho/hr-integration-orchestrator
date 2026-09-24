# Data Mapping: `employee.created` → Canonical Employee

Source: fictional HR core platform event (`app/domain/source_event.py`).
Target: `CanonicalEmployee` (`app/domain/canonical.py`).
Implementation: `app/domain/mapping.py`.

Validation happens in two stages:
1. **Schema validation** at the API boundary (Pydantic). Failure → HTTP 422, `VALIDATION_ERROR`, no run created.
2. **Business rules** during mapping. Failure → run `FAILED`, `BUSINESS_RULE_ERROR`, no downstream calls.

## Envelope

| Source field | Canonical/audit field | Transformation rule | Validation rule | Data-quality note |
|---|---|---|---|---|
| `event_id` | `integration_runs.source_event_id` | None | Required, 1–64 chars, `[A-Za-z0-9._-]` | Idempotency key; must be globally unique per event from the source |
| `event_type` | `integration_runs.event_type` | None | Must equal `employee.created` | Other types are rejected until implemented |
| `occurred_at` | – (not persisted) | Parsed as ISO-8601 datetime | Required, valid datetime | Needed later for out-of-order protection on update events |

## Employee

| Source field | Canonical field | Transformation rule | Validation rule | Data-quality note |
|---|---|---|---|---|
| `employee.employee_id` | `person_id` | Trim, upper-case | Required, pattern `EMP-#####` | Stable key across systems; used as Identity upsert key |
| `employee.first_name` | `given_name` | Trim, collapse internal whitespace | Required, 1–100 chars | PII – never logged |
| `employee.last_name` | `family_name` | Trim, collapse internal whitespace | Required, 1–100 chars | PII – never logged |
| `employee.work_email` | `primary_email` | Trim, lower-case | Required, email syntax, ≤254 chars | PII – masked in logs (`m***@example.test`); deliverability not checked |
| `employee.start_date` | `employment_start_date` | Parsed as ISO date | Required, `YYYY-MM-DD` | Past dates allowed (late hires); used as task due date |
| `employee.department` | `organizational_unit` | Trim, collapse whitespace | Required, 1–100 chars | Free text in source; a production mapping would use a code list |
| `employee.cost_center` | `cost_center_code` | Trim, upper-case | Required, pattern `CC-###` to `CC-######` | Existence in finance master data is not verified |
| `employee.location` | `work_location` | Trim, collapse whitespace | Required, 1–100 chars | Free text; candidate for a location reference table |
| `employee.manager_employee_id` | `manager_id` | Upper-case; empty → `null` | Optional, pattern `EMP-#####`; **business rule:** must differ from `employee_id` | Manager existence is not verified; onboarding task is assigned to manager if present |

## Rejected / unknown fields

Unknown fields are **rejected** (`extra="forbid"`). This prevents unexpected personal data (for example salary or national ID) from silently entering the integration. If the source adds optional fields, the contract is versioned explicitly.

## Downstream projections

| Canonical field | Identity Mgmt | Collaboration | Notification |
|---|---|---|---|
| `person_id` | path + `external_id` | `subject_person_id` | – |
| `given_name` / `family_name` | `given_name` / `family_name` | task title | `variables.given_name` |
| `primary_email` | `email` | – | `recipient` |
| `employment_start_date` | `active_from` | `due_date` | `variables.start_date` |
| `organizational_unit` | `organizational_unit` | `team` | – |
| `cost_center_code` | `cost_center` | – | – |
| `work_location` | – | `location` | `variables.location` |
| `manager_id` | `manager_external_id` | `assignee_person_id` | – |

Each downstream system receives only the fields it needs (data minimization).

