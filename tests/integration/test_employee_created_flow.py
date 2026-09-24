"""End-to-end tests: API -> orchestrator -> HTTP connectors -> mock downstream systems."""

import logging

from app.domain.statuses import RunStatus, StepStatus

URL = "/api/v1/events/employee-created"
PII_VALUES = ["maya.klein@example.test", "Maya", "Klein"]


def _steps(detail: dict) -> dict[str, dict]:
    return {s["step_name"]: s for s in detail["steps"]}


def _detail(env, run_id: str) -> dict:
    response = env.client.get(f"/api/v1/integration-runs/{run_id}")
    assert response.status_code == 200
    return response.json()


# --- Happy path --------------------------------------------------------------------------


def test_happy_path_provisions_all_systems(env, event_payload):
    response = env.client.post(URL, json=event_payload, headers={"X-Correlation-ID": "corr-happy"})

    assert response.status_code == 202
    body = response.json()
    assert body["status"] == RunStatus.SUCCEEDED
    assert body["correlation_id"] == "corr-happy"
    assert body["duplicate"] is False
    assert {"integration_run_id", "received_at"} <= body.keys()
    assert response.headers["X-Correlation-ID"] == "corr-happy"

    detail = _detail(env, body["integration_run_id"])
    assert detail["source_event_id"] == "evt-10001"
    assert detail["retry_count"] == 0
    assert detail["finished_at"] is not None
    assert all(s["status"] == StepStatus.SUCCEEDED for s in detail["steps"])
    assert _steps(detail)["PROVISION_IDENTITY"]["external_reference"].startswith("usr-")
    assert [h["status"] for h in detail["status_history"]] == [
        "RECEIVED",
        "VALIDATED",
        "IN_PROGRESS",
        "SUCCEEDED",
    ]
    assert env.mock_state.users["EMP-10001"]["email"] == "maya.klein@example.test"
    assert len(env.mock_state.tasks) == 1
    assert len(env.mock_state.notifications) == 1


def test_correlation_id_is_generated_when_missing(env, event_payload):
    response = env.client.post(URL, json=event_payload)
    cid = response.json()["correlation_id"]
    assert len(cid) == 36
    assert response.headers["X-Correlation-ID"] == cid


def test_status_endpoints_do_not_expose_pii(env, event_payload):
    run_id = env.client.post(URL, json=event_payload).json()["integration_run_id"]
    detail_text = env.client.get(f"/api/v1/integration-runs/{run_id}").text
    list_text = env.client.get("/api/v1/integration-runs").text
    for value in PII_VALUES:
        assert value not in detail_text
        assert value not in list_text


def test_unknown_run_returns_404(env):
    assert env.client.get("/api/v1/integration-runs/does-not-exist").status_code == 404


def test_health(env):
    assert env.client.get("/health").json() == {"status": "ok", "database": "ok"}


# --- Failure scenario 1: invalid event ---------------------------------------------------


def test_invalid_event_is_rejected_without_echoing_input(env, event_payload):
    event_payload["employee"]["work_email"] = "maya.klein-at-example"
    del event_payload["employee"]["start_date"]

    response = env.client.post(URL, json=event_payload, headers={"X-Correlation-ID": "corr-bad"})

    assert response.status_code == 422
    body = response.json()
    assert body["error_category"] == "VALIDATION_ERROR"
    assert body["correlation_id"] == "corr-bad"
    fields = {d["field"] for d in body["details"]}
    assert {"employee.work_email", "employee.start_date"} <= fields
    assert "maya.klein-at-example" not in response.text
    assert env.mock_state.users == {}
    assert env.client.get("/api/v1/integration-runs").json() == []


def test_business_rule_violation_fails_without_retry(env, event_payload):
    event_payload["employee"]["manager_employee_id"] = "EMP-10001"
    body = env.client.post(URL, json=event_payload).json()
    assert body["status"] == RunStatus.FAILED
    detail = _detail(env, body["integration_run_id"])
    assert detail["error_category"] == "BUSINESS_RULE_ERROR"
    assert _steps(detail)["PROVISION_IDENTITY"]["status"] == StepStatus.SKIPPED
    assert env.sleep.delays == []
    assert env.mock_state.users == {}


# --- Failure scenario 2: transient identity timeout, then success -------------------------


def test_identity_timeout_is_retried_then_succeeds(make_env, event_payload):
    env = make_env(identity_timeout=True, identity_timeout_failures=2)

    body = env.client.post(URL, json=event_payload).json()

    assert body["status"] == RunStatus.SUCCEEDED
    detail = _detail(env, body["integration_run_id"])
    identity = _steps(detail)["PROVISION_IDENTITY"]
    assert identity["attempts"] == 3
    assert identity["status"] == StepStatus.SUCCEEDED
    assert detail["retry_count"] == 2
    assert env.sleep.delays == [0.5, 1.0]
    statuses = [h["status"] for h in detail["status_history"]]
    assert statuses.count("RETRYING") == 2
    assert statuses[-1] == "SUCCEEDED"
    assert len(env.mock_state.users) == 1


# --- Failure scenario 3: permanent collaboration failure -> manual review -----------------


def test_permanent_collaboration_failure_requires_manual_review(make_env, event_payload):
    env = make_env(collaboration_failure=True)

    body = env.client.post(URL, json=event_payload).json()

    assert body["status"] == RunStatus.MANUAL_REVIEW_REQUIRED
    detail = _detail(env, body["integration_run_id"])
    steps = _steps(detail)
    assert detail["error_category"] == "PERMANENT_TECHNICAL_ERROR"
    assert "Collaboration Platform" in detail["error_message"]
    assert steps["PROVISION_IDENTITY"]["status"] == StepStatus.SUCCEEDED
    assert steps["CREATE_ONBOARDING_TASK"]["status"] == StepStatus.FAILED
    assert steps["CREATE_ONBOARDING_TASK"]["attempts"] == 1
    assert steps["SEND_WELCOME_NOTIFICATION"]["status"] == StepStatus.SKIPPED
    assert env.sleep.delays == []

    listed = env.client.get("/api/v1/integration-runs", params={"status": "MANUAL_REVIEW_REQUIRED"})
    assert [r["integration_run_id"] for r in listed.json()] == [body["integration_run_id"]]
    assert env.client.get("/api/v1/integration-runs", params={"status": "SUCCEEDED"}).json() == []


# --- Additional: retry exhaustion -------------------------------------------------------


def test_notification_outage_exhausts_retries_and_requires_manual_review(make_env, event_payload):
    env = make_env(notification_failure=True)

    body = env.client.post(URL, json=event_payload).json()

    assert body["status"] == RunStatus.MANUAL_REVIEW_REQUIRED
    detail = _detail(env, body["integration_run_id"])
    notify = _steps(detail)["SEND_WELCOME_NOTIFICATION"]
    assert notify["attempts"] == 4
    assert notify["error_category"] == "TRANSIENT_TECHNICAL_ERROR"
    assert detail["retry_count"] == 3
    assert env.sleep.delays == [0.5, 1.0, 2.0]
    assert detail["status_history"][-1]["note"] == "Retry limit exhausted"


def test_invalid_status_filter_is_rejected(env):
    assert env.client.get("/api/v1/integration-runs", params={"status": "BOGUS"}).status_code == 422


# --- Idempotency ------------------------------------------------------------------------


def test_duplicate_event_does_not_provision_twice(env, event_payload):
    first = env.client.post(URL, json=event_payload).json()
    second = env.client.post(URL, json=event_payload).json()
    third = env.client.post(URL, json=event_payload).json()

    assert second["duplicate"] is True and third["duplicate"] is True
    assert (
        first["integration_run_id"] == second["integration_run_id"] == third["integration_run_id"]
    )
    assert len(env.mock_state.users) == 1
    assert len(env.mock_state.tasks) == 1
    assert len(env.mock_state.notifications) == 1
    assert len(env.client.get("/api/v1/integration-runs").json()) == 1


def test_new_event_for_same_employee_updates_instead_of_duplicating(env, event_payload):
    env.client.post(URL, json=event_payload)
    event_payload["event_id"] = "evt-10002"
    env.client.post(URL, json=event_payload)
    assert len(env.mock_state.users) == 1


# --- Privacy in logs --------------------------------------------------------------------


def test_operational_logs_mask_email_addresses(make_env, event_payload, caplog):
    env = make_env(identity_timeout=True, identity_timeout_failures=1)
    with caplog.at_level(logging.DEBUG):
        env.client.post(URL, json=event_payload)
        bad = dict(event_payload, event_id="evt-bad")
        bad["employee"] = dict(event_payload["employee"], start_date="invalid")
        env.client.post(URL, json=bad)

    app_records = [r for r in caplog.records if r.name.startswith("app")]
    assert app_records, "expected application log records"
    for record in app_records:
        rendered = record.getMessage() + " " + str(record.__dict__)
        assert "maya.klein@example.test" not in rendered
        assert "Klein" not in rendered
