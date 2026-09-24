"""Connector interfaces and a shared HTTP base implementation."""

from dataclasses import dataclass
from typing import Any, Protocol

import httpx

from app.domain.canonical import CanonicalEmployee
from app.domain.errors import ErrorCategory, IntegrationError, classify_exception


@dataclass(frozen=True)
class ConnectorResult:
    """Non-sensitive reference returned by a downstream system."""

    external_reference: str
    created: bool = True


class IdentityConnector(Protocol):
    def upsert_user(self, employee: CanonicalEmployee, correlation_id: str) -> ConnectorResult: ...


class CollaborationConnector(Protocol):
    def create_onboarding_task(
        self, employee: CanonicalEmployee, idempotency_key: str, correlation_id: str
    ) -> ConnectorResult: ...


class NotificationConnector(Protocol):
    def send_welcome(
        self, employee: CanonicalEmployee, idempotency_key: str, correlation_id: str
    ) -> ConnectorResult: ...


class HttpConnector:
    """Shared HTTP plumbing: base URL, timeout, correlation header and error classification."""

    system_name = "Downstream system"

    def __init__(
        self,
        base_url: str = "",
        timeout_seconds: float = 5.0,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=base_url, timeout=timeout_seconds, transport=transport
        )

    def _request(
        self,
        method: str,
        path: str,
        correlation_id: str,
        json: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> httpx.Response:
        headers = {"X-Correlation-ID": correlation_id}
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        try:
            response = self._client.request(method, path, json=json, headers=headers)
            response.raise_for_status()
        except Exception as exc:  # classified into a safe IntegrationError
            raise classify_exception(exc, self.system_name) from exc
        return response

    def _reference(self, response: httpx.Response, key: str) -> str:
        try:
            return str(response.json()[key])
        except (ValueError, KeyError, TypeError) as exc:
            raise IntegrationError(
                ErrorCategory.PERMANENT_TECHNICAL_ERROR,
                f"{self.system_name} returned an unexpected response body.",
            ) from exc

    def close(self) -> None:
        self._client.close()
