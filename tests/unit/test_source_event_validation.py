import pytest
from pydantic import ValidationError

from app.domain.source_event import EmployeeCreatedEvent


def test_valid_event_is_accepted(event_payload):
    event = EmployeeCreatedEvent.model_validate(event_payload)
    assert event.event_id == "evt-10001"
    assert event.employee.employee_id == "EMP-10001"


def test_manager_is_optional(event_payload):
    del event_payload["employee"]["manager_employee_id"]
    assert EmployeeCreatedEvent.model_validate(event_payload).employee.manager_employee_id is None


@pytest.mark.parametrize(
    "field",
    ["employee_id", "first_name", "last_name", "work_email", "start_date", "cost_center"],
)
def test_missing_required_employee_field_is_rejected(event_payload, field):
    del event_payload["employee"][field]
    with pytest.raises(ValidationError) as info:
        EmployeeCreatedEvent.model_validate(event_payload)
    assert any(err["loc"][-1] == field for err in info.value.errors())


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("work_email", "not-an-email"),
        ("employee_id", "10001"),
        ("cost_center", "100"),
        ("start_date", "01-10-2026"),
        ("first_name", ""),
        ("manager_employee_id", "BOSS"),
    ],
)
def test_malformed_employee_field_is_rejected(event_payload, field, value):
    event_payload["employee"][field] = value
    with pytest.raises(ValidationError):
        EmployeeCreatedEvent.model_validate(event_payload)


def test_wrong_event_type_is_rejected(event_payload):
    event_payload["event_type"] = "employee.terminated"
    with pytest.raises(ValidationError):
        EmployeeCreatedEvent.model_validate(event_payload)


def test_unknown_fields_are_rejected(event_payload):
    event_payload["employee"]["salary"] = 100000
    with pytest.raises(ValidationError):
        EmployeeCreatedEvent.model_validate(event_payload)


def test_unsafe_event_id_is_rejected(event_payload):
    event_payload["event_id"] = "evt 1; DROP TABLE"
    with pytest.raises(ValidationError):
        EmployeeCreatedEvent.model_validate(event_payload)
