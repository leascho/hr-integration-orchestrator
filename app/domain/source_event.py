"""Source event contract as emitted by the fictional HR core platform."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EMPLOYEE_ID_PATTERN = r"^EMP-\d{5}$"
# Pragmatic syntax check. Reserved test domains such as example.test are intentionally allowed.
EMAIL_PATTERN = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}$"


class SourceEmployee(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    employee_id: str = Field(pattern=EMPLOYEE_ID_PATTERN, examples=["EMP-10001"])
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    work_email: str = Field(max_length=254, pattern=EMAIL_PATTERN)

    start_date: date
    department: str = Field(min_length=1, max_length=100)
    cost_center: str = Field(pattern=r"^CC-\d{3,6}$", examples=["CC-100"])
    location: str = Field(min_length=1, max_length=100)
    manager_employee_id: str | None = Field(default=None, pattern=EMPLOYEE_ID_PATTERN)


class EmployeeCreatedEvent(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "example": {
                "event_id": "evt-10001",
                "event_type": "employee.created",
                "occurred_at": "2026-09-24T10:30:00Z",
                "employee": {
                    "employee_id": "EMP-10001",
                    "first_name": "Maya",
                    "last_name": "Klein",
                    "work_email": "maya.klein@example.test",
                    "start_date": "2026-10-01",
                    "department": "Technology",
                    "cost_center": "CC-100",
                    "location": "Amsterdam",
                    "manager_employee_id": "EMP-00042",
                },
            }
        },
    )

    event_id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    event_type: Literal["employee.created"]
    occurred_at: datetime
    employee: SourceEmployee
