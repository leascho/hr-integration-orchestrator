"""Connector for the fictional Collaboration Platform."""

from app.connectors.base import ConnectorResult, HttpConnector
from app.domain.canonical import CanonicalEmployee


class HttpCollaborationConnector(HttpConnector):
    system_name = "Collaboration Platform"

    def create_onboarding_task(
        self, employee: CanonicalEmployee, idempotency_key: str, correlation_id: str
    ) -> ConnectorResult:
        response = self._request(
            "POST",
            "/api/v1/tasks",
            correlation_id,
            idempotency_key=idempotency_key,
            json={
                "title": f"Onboarding: {employee.display_name}",
                "task_type": "ONBOARDING",
                "subject_person_id": employee.person_id,
                "assignee_person_id": employee.manager_id,
                "due_date": employee.employment_start_date.isoformat(),
                "team": employee.organizational_unit,
                "location": employee.work_location,
            },
        )
        return ConnectorResult(
            external_reference=self._reference(response, "task_id"),
            created=response.status_code == 201,
        )
