"""Connector for the fictional Notification Service."""

from app.connectors.base import ConnectorResult, HttpConnector
from app.domain.canonical import CanonicalEmployee


class HttpNotificationConnector(HttpConnector):
    system_name = "Notification Service"

    def send_welcome(
        self, employee: CanonicalEmployee, idempotency_key: str, correlation_id: str
    ) -> ConnectorResult:
        response = self._request(
            "POST",
            "/api/v1/notifications",
            correlation_id,
            idempotency_key=idempotency_key,
            json={
                "template": "WELCOME_NEW_EMPLOYEE",
                "channel": "EMAIL",
                "recipient": employee.primary_email,
                "variables": {
                    "given_name": employee.given_name,
                    "start_date": employee.employment_start_date.isoformat(),
                    "location": employee.work_location,
                },
            },
        )
        return ConnectorResult(
            external_reference=self._reference(response, "notification_id"),
            created=response.status_code == 201,
        )
