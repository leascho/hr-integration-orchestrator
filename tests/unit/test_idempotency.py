"""Idempotency at repository and orchestrator level, with fake connectors."""

import pytest

from app.connectors.base import ConnectorResult
from app.domain.source_event import EmployeeCreatedEvent
from app.domain.statuses import RunStatus, StepName
from app.orchestration.orchestrator import EmployeeCreatedOrchestrator
from app.orchestration.retry import RetryPolicy
from app.persistence.db import build_engine, build_session_factory, init_db
from app.persistence.repository import DuplicateEventError, IntegrationRunRepository


class CountingConnector:
    def __init__(self) -> None:
        self.calls = 0

    def _call(self, *args, **kwargs) -> ConnectorResult:
        self.calls += 1
        return ConnectorResult(external_reference=f"ref-{self.calls}")

    upsert_user = _call
    create_onboarding_task = _call
    send_welcome = _call


@pytest.fixture
def repository():
    engine = build_engine("sqlite:///:memory:")
    init_db(engine)
    session = build_session_factory(engine)()
    yield IntegrationRunRepository(session)
    session.close()


def test_repository_rejects_second_run_for_same_event(repository):
    first = repository.create_run(
        source_event_id="evt-1", event_type="employee.created", correlation_id="c1", steps=[]
    )
    with pytest.raises(DuplicateEventError) as info:
        repository.create_run(
            source_event_id="evt-1", event_type="employee.created", correlation_id="c2", steps=[]
        )
    assert info.value.existing.id == first.id


def test_run_is_created_with_pending_steps_and_received_history(repository):
    run = repository.create_run(
        source_event_id="evt-2",
        event_type="employee.created",
        correlation_id="c1",
        steps=[StepName.PROVISION_IDENTITY, StepName.CREATE_ONBOARDING_TASK],
    )
    assert run.status == RunStatus.RECEIVED
    assert [s.sequence for s in run.steps] == [1, 2]
    assert [h.status for h in run.history] == [RunStatus.RECEIVED]


def test_duplicate_event_does_not_call_connectors_again(repository, event_payload):
    identity, collab, notify = CountingConnector(), CountingConnector(), CountingConnector()
    orchestrator = EmployeeCreatedOrchestrator(
        repository, identity, collab, notify, RetryPolicy(sleep=lambda _: None)
    )
    event = EmployeeCreatedEvent.model_validate(event_payload)

    first = orchestrator.process(event, "corr-1")
    second = orchestrator.process(event, "corr-2")

    assert first.run.status == RunStatus.SUCCEEDED
    assert second.duplicate is True
    assert second.run.id == first.run.id
    assert (identity.calls, collab.calls, notify.calls) == (1, 1, 1)
