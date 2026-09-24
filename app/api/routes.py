"""HTTP routes."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import text

from app.api.dependencies import get_correlation_id, get_orchestrator, get_repository
from app.api.schemas import (
    ErrorResponse,
    EventAcceptedResponse,
    HealthResponse,
    IntegrationRunDetail,
    IntegrationRunSummary,
    StatusHistoryView,
    StepView,
)
from app.domain.source_event import EmployeeCreatedEvent
from app.domain.statuses import RunStatus
from app.orchestration.orchestrator import EmployeeCreatedOrchestrator
from app.persistence.models import IntegrationRun
from app.persistence.repository import IntegrationRunRepository

router = APIRouter()


def _detail(run: IntegrationRun) -> IntegrationRunDetail:
    return IntegrationRunDetail(
        integration_run_id=run.id,
        correlation_id=run.correlation_id,
        source_event_id=run.source_event_id,
        event_type=run.event_type,
        status=run.status,
        error_category=run.error_category,
        error_message=run.error_message,
        retry_count=run.retry_count,
        received_at=run.received_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        steps=[StepView.model_validate(s, from_attributes=True) for s in run.steps],
        status_history=[
            StatusHistoryView.model_validate(h, from_attributes=True) for h in run.history
        ],
    )


@router.post(
    "/api/v1/events/employee-created",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=EventAcceptedResponse,
    responses={422: {"model": ErrorResponse}},
    tags=["events"],
    summary="Submit an employee.created event from the HR core platform",
)
def submit_employee_created(
    event: EmployeeCreatedEvent,
    correlation_id: Annotated[str, Depends(get_correlation_id)],
    orchestrator: Annotated[EmployeeCreatedOrchestrator, Depends(get_orchestrator)],
) -> EventAcceptedResponse:
    outcome = orchestrator.process(event, correlation_id)
    run = outcome.run
    return EventAcceptedResponse(
        integration_run_id=run.id,
        correlation_id=run.correlation_id,
        status=run.status,
        received_at=run.received_at,
        duplicate=outcome.duplicate,
    )


@router.get(
    "/api/v1/integration-runs/{integration_run_id}",
    response_model=IntegrationRunDetail,
    responses={404: {"model": ErrorResponse}},
    tags=["operations"],
)
def get_integration_run(
    integration_run_id: str,
    repository: Annotated[IntegrationRunRepository, Depends(get_repository)],
) -> IntegrationRunDetail:
    run = repository.get(integration_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Integration run not found.")
    return _detail(run)


@router.get(
    "/api/v1/integration-runs",
    response_model=list[IntegrationRunSummary],
    tags=["operations"],
)
def list_integration_runs(
    repository: Annotated[IntegrationRunRepository, Depends(get_repository)],
    run_status: Annotated[RunStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[IntegrationRunSummary]:
    runs = repository.list_runs(status=run_status, limit=limit)
    return [
        IntegrationRunSummary(
            integration_run_id=r.id,
            correlation_id=r.correlation_id,
            source_event_id=r.source_event_id,
            event_type=r.event_type,
            status=r.status,
            error_category=r.error_category,
            retry_count=r.retry_count,
            received_at=r.received_at,
            finished_at=r.finished_at,
        )
        for r in runs
    ]


@router.get("/health", response_model=HealthResponse, tags=["operations"])
def health(request: Request) -> HealthResponse:
    try:
        with request.app.state.engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return HealthResponse(status="ok", database="ok")
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc
