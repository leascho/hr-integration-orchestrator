"""Mapping from the HR core source contract to the canonical employee model.

See docs/data-mapping.md for the field-level specification.
"""

from app.domain.canonical import CanonicalEmployee
from app.domain.errors import ErrorCategory, IntegrationError
from app.domain.source_event import SourceEmployee


def _normalize_name(value: str) -> str:
    return " ".join(value.split())


def map_to_canonical(source: SourceEmployee) -> CanonicalEmployee:
    manager_id = source.manager_employee_id or None
    if manager_id == source.employee_id:
        raise IntegrationError(
            ErrorCategory.BUSINESS_RULE_ERROR,
            "An employee cannot be their own manager.",
        )
    return CanonicalEmployee(
        person_id=source.employee_id.upper(),
        given_name=_normalize_name(source.first_name),
        family_name=_normalize_name(source.last_name),
        primary_email=str(source.work_email).lower(),
        employment_start_date=source.start_date,
        organizational_unit=_normalize_name(source.department),
        cost_center_code=source.cost_center.upper(),
        work_location=_normalize_name(source.location),
        manager_id=manager_id.upper() if manager_id else None,
    )
