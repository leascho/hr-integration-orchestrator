"""Application factory."""

from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.dependencies import resolve_correlation_id
from app.api.routes import router
from app.config import Settings, get_settings
from app.connectors.base import CollaborationConnector, IdentityConnector, NotificationConnector
from app.connectors.collaboration import HttpCollaborationConnector
from app.connectors.identity import HttpIdentityConnector
from app.connectors.notification import HttpNotificationConnector
from app.domain.errors import ErrorCategory
from app.logging_config import configure_logging, correlation_id_var, get_logger
from app.orchestration.retry import RetryPolicy
from app.persistence.db import build_engine, build_session_factory, init_db

logger = get_logger(__name__)


@dataclass
class Connectors:
    identity: IdentityConnector
    collaboration: CollaborationConnector
    notification: NotificationConnector


def build_http_connectors(settings: Settings) -> Connectors:
    timeout = settings.connector_timeout_seconds
    return Connectors(
        identity=HttpIdentityConnector(settings.identity_service_base_url, timeout),
        collaboration=HttpCollaborationConnector(settings.collaboration_service_base_url, timeout),
        notification=HttpNotificationConnector(settings.notification_service_base_url, timeout),
    )


def create_app(
    settings: Settings | None = None,
    connectors: Connectors | None = None,
    retry_policy: RetryPolicy | None = None,
    configure_logs: bool = True,
) -> FastAPI:
    settings = settings or get_settings()
    if configure_logs:
        configure_logging(settings.log_level)

    app = FastAPI(
        title="HR Integration Orchestrator",
        version="0.1.0",
        description=(
            "Portfolio project orchestrating a fictional employee.created lifecycle event "
            "across fictional downstream systems. All systems and data are fictional."
        ),
    )
    engine = build_engine(settings.database_url)
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = build_session_factory(engine)
    app.state.connectors = connectors or build_http_connectors(settings)
    app.state.retry_policy = retry_policy or RetryPolicy(
        max_retries=settings.retry_max_retries,
        base_delay_seconds=settings.retry_base_delay_seconds,
        max_delay_seconds=settings.retry_max_delay_seconds,
    )

    @app.middleware("http")
    async def correlation_header(request: Request, call_next):
        cid = resolve_correlation_id(request.headers.get("X-Correlation-ID"))
        token = correlation_id_var.set(cid)
        try:
            response = await call_next(request)
        finally:
            correlation_id_var.reset(token)
        response.headers["X-Correlation-ID"] = cid
        return response

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Never echo the submitted input back: it may contain employee PII.
        details = [
            {
                "field": ".".join(str(p) for p in err.get("loc", []) if p != "body") or "body",
                "message": err.get("msg", "Invalid value"),
            }
            for err in exc.errors()
        ]
        cid = correlation_id_var.get() or resolve_correlation_id(None)
        logger.info(
            "Rejected invalid request",
            extra={"path": request.url.path, "error_count": len(details), "correlation_id": cid},
        )
        return JSONResponse(
            status_code=422,
            headers={"X-Correlation-ID": cid},
            content={
                "error_category": ErrorCategory.VALIDATION_ERROR,
                "message": "The request payload failed validation.",
                "correlation_id": cid,
                "details": details,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"message": exc.detail})

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(
            "Unhandled error", extra={"path": request.url.path, "error_type": type(exc).__name__}
        )
        return JSONResponse(
            status_code=500,
            content={
                "error_category": ErrorCategory.PERMANENT_TECHNICAL_ERROR,
                "message": "An internal error occurred.",
            },
        )

    app.include_router(router)
    return app
