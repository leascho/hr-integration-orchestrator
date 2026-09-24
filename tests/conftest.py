"""Shared fixtures. All data is fictional."""

import copy
import os
from collections.abc import Callable

# Ensure no accidental dependency on a developer's local environment.
os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.connectors.collaboration import HttpCollaborationConnector
from app.connectors.identity import HttpIdentityConnector
from app.connectors.notification import HttpNotificationConnector
from app.main import Connectors, create_app
from app.orchestration.retry import RetryPolicy
from mock_services.app import SimulationConfig, create_mock_app

SAMPLE_EVENT = {
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


@pytest.fixture
def event_payload() -> dict:
    return copy.deepcopy(SAMPLE_EVENT)


class RecordingSleep:
    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


@pytest.fixture
def recording_sleep() -> RecordingSleep:
    return RecordingSleep()


class Environment:
    """Orchestrator API wired to in-process mock downstream systems over real HTTP semantics."""

    def __init__(self, simulation: SimulationConfig, sleep: RecordingSleep) -> None:
        self.mock_app = create_mock_app(simulation)
        self.sleep = sleep

        def mock_client(prefix: str) -> TestClient:
            return TestClient(self.mock_app, base_url=f"http://mock-downstream/{prefix}")

        connectors = Connectors(
            identity=HttpIdentityConnector(client=mock_client("identity")),
            collaboration=HttpCollaborationConnector(client=mock_client("collaboration")),
            notification=HttpNotificationConnector(client=mock_client("notification")),
        )
        self.app = create_app(
            settings=Settings(database_url="sqlite:///:memory:"),
            connectors=connectors,
            retry_policy=RetryPolicy(
                max_retries=3, base_delay_seconds=0.5, max_delay_seconds=4.0, sleep=sleep
            ),
            configure_logs=False,
        )
        self.client = TestClient(self.app)

    @property
    def mock_state(self):
        return self.mock_app.state.mock_state


@pytest.fixture
def make_env(recording_sleep: RecordingSleep) -> Callable[..., Environment]:
    def _factory(**simulation: object) -> Environment:
        return Environment(SimulationConfig(**simulation), recording_sleep)

    return _factory


@pytest.fixture
def env(make_env) -> Environment:
    return make_env()
