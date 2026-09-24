"""Connector tests using httpx.MockTransport (no network)."""

import json

import httpx
import pytest

from app.connectors.collaboration import HttpCollaborationConnector
from app.connectors.identity import HttpIdentityConnector
from app.connectors.notification import HttpNotificationConnector
from app.domain.errors import ErrorCategory, IntegrationError
from app.domain.mapping import map_to_canonical
from app.domain.source_event import EmployeeCreatedEvent


@pytest.fixture
def employee(event_payload):
    return map_to_canonical(EmployeeCreatedEvent.model_validate(event_payload).employee)


def _transport(captured: list, status: int = 201, body: dict | None = None, exc=None):
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if exc:
            raise exc
        return httpx.Response(status, json=body or {})

    return httpx.MockTransport(handler)


def test_identity_upsert_uses_put_with_person_id_and_correlation(employee):
    captured: list[httpx.Request] = []
    conn = HttpIdentityConnector(
        "http://identity.invalid", transport=_transport(captured, 201, {"user_id": "usr-1"})
    )
    result = conn.upsert_user(employee, "corr-1")

    request = captured[0]
    assert request.method == "PUT"
    assert request.url.path == "/api/v1/users/EMP-10001"
    assert request.headers["X-Correlation-ID"] == "corr-1"
    assert json.loads(request.content)["email"] == "maya.klein@example.test"
    assert result.external_reference == "usr-1"
    assert result.created is True


def test_identity_update_reports_not_created(employee):
    conn = HttpIdentityConnector(
        "http://identity.invalid", transport=_transport([], 200, {"user_id": "usr-1"})
    )
    assert conn.upsert_user(employee, "c").created is False


def test_collaboration_sends_idempotency_key(employee):
    captured: list[httpx.Request] = []
    conn = HttpCollaborationConnector(
        "http://collab.invalid/base", transport=_transport(captured, 201, {"task_id": "tsk-1"})
    )
    result = conn.create_onboarding_task(employee, "evt-1:task", "corr-1")
    assert captured[0].url.path == "/base/api/v1/tasks"
    assert captured[0].headers["Idempotency-Key"] == "evt-1:task"
    assert json.loads(captured[0].content)["assignee_person_id"] == "EMP-00042"
    assert result.external_reference == "tsk-1"


def test_notification_sends_welcome_template(employee):
    captured: list[httpx.Request] = []
    conn = HttpNotificationConnector(
        "http://notify.invalid", transport=_transport(captured, 201, {"notification_id": "n-1"})
    )
    assert conn.send_welcome(employee, "k", "c").external_reference == "n-1"
    assert json.loads(captured[0].content)["template"] == "WELCOME_NEW_EMPLOYEE"


@pytest.mark.parametrize(
    ("status", "category"),
    [
        (401, ErrorCategory.AUTHENTICATION_ERROR),
        (503, ErrorCategory.TRANSIENT_TECHNICAL_ERROR),
        (500, ErrorCategory.PERMANENT_TECHNICAL_ERROR),
        (409, ErrorCategory.BUSINESS_RULE_ERROR),
    ],
)
def test_http_errors_are_classified(employee, status, category):
    conn = HttpIdentityConnector("http://identity.invalid", transport=_transport([], status))
    with pytest.raises(IntegrationError) as info:
        conn.upsert_user(employee, "c")
    assert info.value.category == category
    assert "Identity Management System" in info.value.safe_message


def test_timeout_is_classified_as_transient(employee):
    transport = _transport([], exc=httpx.ReadTimeout("slow"))
    conn = HttpIdentityConnector("http://identity.invalid", transport=transport)
    with pytest.raises(IntegrationError) as info:
        conn.upsert_user(employee, "c")
    assert info.value.category == ErrorCategory.TRANSIENT_TECHNICAL_ERROR


def test_connection_refused_is_dependency_unavailable(employee):
    transport = _transport([], exc=httpx.ConnectError("refused"))
    conn = HttpNotificationConnector("http://notify.invalid", transport=transport)
    with pytest.raises(IntegrationError) as info:
        conn.send_welcome(employee, "k", "c")
    assert info.value.category == ErrorCategory.DEPENDENCY_UNAVAILABLE


def test_unexpected_response_body_is_permanent_error(employee):
    conn = HttpIdentityConnector("http://identity.invalid", transport=_transport([], 201, {}))
    with pytest.raises(IntegrationError) as info:
        conn.upsert_user(employee, "c")
    assert info.value.category == ErrorCategory.PERMANENT_TECHNICAL_ERROR
