"""Canonical employee model, independent from any source system."""

from datetime import date

from pydantic import BaseModel, ConfigDict


class CanonicalEmployee(BaseModel):
    model_config = ConfigDict(frozen=True)

    person_id: str
    given_name: str
    family_name: str
    primary_email: str
    employment_start_date: date
    organizational_unit: str
    cost_center_code: str
    work_location: str
    manager_id: str | None

    @property
    def display_name(self) -> str:
        return f"{self.given_name} {self.family_name}"
