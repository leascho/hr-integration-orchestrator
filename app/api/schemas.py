"""API response schemas. None of these contain employee PII."""

from datetime import datetime

from pydantic import BaseModel


class EventAcceptedResponse(BaseModel):
    integration_run_id: str
    correlation_id: str
    status: str
    received_at: datetime
    duplicate: bool = False


class StepView(BaseModel):
    sequence: int
    step_name: str
    status: str
    attempts: int
    error_category: str | None
    error_message: str | None
    external_reference: str | None
    started_at: datetime | None
    finished_at: datetime | None


class StatusHistoryView(BaseModel):
    status: str
    note: str | None
    occurred_at: datetime


class IntegrationRunDetail(BaseModel):
    integration_run_id: str
    correlation_id: str
    source_event_id: str
    event_type: str
    status: str
    error_category: str | None
    error_message: str | None
    retry_count: int
    received_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    steps: list[StepView]
    status_history: list[StatusHistoryView]


class IntegrationRunSummary(BaseModel):
    integration_run_id: str
    correlation_id: str
    source_event_id: str
    event_type: str
    status: str
    error_category: str | None
    retry_count: int
    received_at: datetime
    finished_at: datetime | None


class ErrorDetail(BaseModel):
    field: str
    message: str


class ErrorResponse(BaseModel):
    error_category: str
    message: str
    correlation_id: str | None = None
    details: list[ErrorDetail] = []


class HealthResponse(BaseModel):
    status: str
    database: str
