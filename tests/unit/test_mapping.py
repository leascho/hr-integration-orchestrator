from datetime import date

import pytest

from app.domain.errors import ErrorCategory, IntegrationError
from app.domain.mapping import map_to_canonical
from app.domain.source_event import EmployeeCreatedEvent


def _source(payload):
    return EmployeeCreatedEvent.model_validate(payload).employee


def test_maps_all_fields(event_payload):
    canonical = map_to_canonical(_source(event_payload))
    assert canonical.model_dump() == {
        "person_id": "EMP-10001",
        "given_name": "Maya",
        "family_name": "Klein",
        "primary_email": "maya.klein@example.test",
        "employment_start_date": date(2026, 10, 1),
        "organizational_unit": "Technology",
        "cost_center_code": "CC-100",
        "work_location": "Amsterdam",
        "manager_id": "EMP-00042",
    }


def test_normalizes_whitespace_and_email_case(event_payload):
    event_payload["employee"].update(
        first_name="  Anna   Lena ",
        work_email="Anna.Berg@Example.TEST",
        location=" Rotterdam ",
    )
    canonical = map_to_canonical(_source(event_payload))
    assert canonical.given_name == "Anna Lena"
    assert canonical.primary_email == "anna.berg@example.test"
    assert canonical.work_location == "Rotterdam"


def test_missing_manager_maps_to_none(event_payload):
    event_payload["employee"]["manager_employee_id"] = None
    assert map_to_canonical(_source(event_payload)).manager_id is None


def test_self_management_is_a_business_rule_error(event_payload):
    event_payload["employee"]["manager_employee_id"] = "EMP-10001"
    with pytest.raises(IntegrationError) as info:
        map_to_canonical(_source(event_payload))
    assert info.value.category == ErrorCategory.BUSINESS_RULE_ERROR
    assert not info.value.retryable


def test_display_name(event_payload):
    assert map_to_canonical(_source(event_payload)).display_name == "Maya Klein"
