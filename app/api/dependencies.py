"""FastAPI dependencies: correlation ID, DB session and orchestrator wiring."""

import re
import uuid
from collections.abc import Iterator

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.logging_config import correlation_id_var
from app.orchestration.orchestrator import EmployeeCreatedOrchestrator
from app.persistence.repository import IntegrationRunRepository

_SAFE_CORRELATION_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


def resolve_correlation_id(value: str | None) -> str:
    """Use the caller's ID if it is well-formed; otherwise generate a UUID."""
    if value and _SAFE_CORRELATION_ID.match(value):
        return value
    return str(uuid.uuid4())


def get_correlation_id(
    x_correlation_id: str | None = Header(
        default=None,
        alias="X-Correlation-ID",
        description="Optional caller-supplied correlation ID. A UUID is generated if absent.",
    ),
) -> str:
    # The middleware resolves the ID once per request and binds it to the context variable.
    correlation_id = correlation_id_var.get() or resolve_correlation_id(x_correlation_id)
    correlation_id_var.set(correlation_id)
    return correlation_id


def get_session(request: Request) -> Iterator[Session]:
    session = request.app.state.session_factory()
    try:
        yield session
    finally:
        session.close()


def get_repository(session: Session = Depends(get_session)) -> IntegrationRunRepository:
    return IntegrationRunRepository(session)


def get_orchestrator(
    request: Request, repository: IntegrationRunRepository = Depends(get_repository)
) -> EmployeeCreatedOrchestrator:
    c = request.app.state.connectors
    return EmployeeCreatedOrchestrator(
        repository=repository,
        identity=c.identity,
        collaboration=c.collaboration,
        notification=c.notification,
        retry_policy=request.app.state.retry_policy,
    )
