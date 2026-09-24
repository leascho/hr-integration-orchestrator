"""Mock downstream systems (local development and demos only)."""

import os
import threading
import uuid
from typing import Any

from fastapi import FastAPI, Header, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel


def _flag(name: str) -> bool:
    return os.getenv(name, "false").strip().lower() in {"1", "true", "yes"}


class SimulationConfig(BaseModel):
    identity_timeout: bool = False
    identity_timeout_failures: int = 2
    collaboration_failure: bool = False
    notification_failure: bool = False


class MockState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        self.users: dict[str, dict[str, Any]] = {}
        self.tasks: dict[str, dict[str, Any]] = {}
        self.notifications: dict[str, dict[str, Any]] = {}
        self.identity_attempts: dict[str, int] = {}


def create_mock_app(simulation: SimulationConfig | None = None) -> FastAPI:
    app = FastAPI(title="Mock Downstream Systems (fictional)", version="0.1.0")
    state = MockState()
    sim = simulation or SimulationConfig(
        identity_timeout=_flag("SIMULATE_IDENTITY_TIMEOUT"),
        identity_timeout_failures=int(os.getenv("SIMULATE_IDENTITY_TIMEOUT_FAILURES", "2")),
        collaboration_failure=_flag("SIMULATE_COLLABORATION_FAILURE"),
        notification_failure=_flag("SIMULATE_NOTIFICATION_FAILURE"),
    )
    app.state.mock_state = state
    app.state.simulation = sim

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/_simulation")
    def get_simulation() -> SimulationConfig:
        return app.state.simulation

    @app.put("/_simulation")
    def set_simulation(config: SimulationConfig) -> SimulationConfig:
        app.state.simulation = config
        with state.lock:
            state.identity_attempts.clear()
        return config

    @app.get("/_stats")
    def stats() -> dict[str, int]:
        return {
            "users": len(state.users),
            "tasks": len(state.tasks),
            "notifications": len(state.notifications),
        }

    # --- Identity Management System -------------------------------------------------
    @app.put("/identity/api/v1/users/{person_id}")
    def upsert_user(person_id: str, body: dict[str, Any], response: Response):
        current = app.state.simulation
        with state.lock:
            attempts = state.identity_attempts.get(person_id, 0) + 1
            state.identity_attempts[person_id] = attempts
            if current.identity_timeout and attempts <= current.identity_timeout_failures:
                return JSONResponse(status_code=504, content={"error": "upstream timeout"})
            if person_id in state.users:
                state.users[person_id].update(body)
                response.status_code = 200
            else:
                state.users[person_id] = {"user_id": f"usr-{uuid.uuid4().hex[:12]}", **body}
                response.status_code = 201
            return {"user_id": state.users[person_id]["user_id"]}

    # --- Collaboration Platform -----------------------------------------------------
    @app.post("/collaboration/api/v1/tasks")
    def create_task(
        body: dict[str, Any],
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ):
        if app.state.simulation.collaboration_failure:
            return JSONResponse(status_code=500, content={"error": "workspace provisioning failed"})
        with state.lock:
            if idempotency_key in state.tasks:
                response.status_code = 200
            else:
                state.tasks[idempotency_key] = {"task_id": f"tsk-{uuid.uuid4().hex[:12]}", **body}
                response.status_code = 201
            return {"task_id": state.tasks[idempotency_key]["task_id"]}

    # --- Notification Service -------------------------------------------------------
    @app.post("/notification/api/v1/notifications")
    def send_notification(
        body: dict[str, Any],
        response: Response,
        idempotency_key: str = Header(alias="Idempotency-Key"),
    ):
        if app.state.simulation.notification_failure:
            return JSONResponse(status_code=503, content={"error": "service unavailable"})
        with state.lock:
            if idempotency_key in state.notifications:
                response.status_code = 200
            else:
                state.notifications[idempotency_key] = {
                    "notification_id": f"ntf-{uuid.uuid4().hex[:12]}"
                }
                response.status_code = 201
            return {"notification_id": state.notifications[idempotency_key]["notification_id"]}

    return app


app = create_mock_app()
