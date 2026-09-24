"""Connector for the fictional Identity Management System."""

from app.connectors.base import ConnectorResult, HttpConnector
from app.domain.canonical import CanonicalEmployee


class HttpIdentityConnector(HttpConnector):
    """Creates or updates a user. PUT keyed by person_id makes the call naturally idempotent."""

    system_name = "Identity Management System"

    def upsert_user(self, employee: CanonicalEmployee, correlation_id: str) -> ConnectorResult:
        response = self._request(
            "PUT",
            f"/api/v1/users/{employee.person_id}",
            correlation_id,
            json={
                "external_id": employee.person_id,
                "given_name": employee.given_name,
                "family_name": employee.family_name,
                "email": employee.primary_email,
                "organizational_unit": employee.organizational_unit,
                "cost_center": employee.cost_center_code,
                "manager_external_id": employee.manager_id,
                "active_from": employee.employment_start_date.isoformat(),
            },
        )
        return ConnectorResult(
            external_reference=self._reference(response, "user_id"),
            created=response.status_code == 201,
        )
