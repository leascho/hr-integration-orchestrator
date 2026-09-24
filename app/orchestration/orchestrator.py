"""Orchestration of the employee.created integration flow."""

from collections.abc import Callable
from dataclasses import dataclass

from app.connectors.base import (
    CollaborationConnector,
    ConnectorResult,
    IdentityConnector,
    NotificationConnector,
)
from app.domain.canonical import CanonicalEmployee
from app.domain.errors import (
    SOURCE_CORRECTION_CATEGORIES,
    IntegrationError,
    classify_exception,
)
from app.domain.mapping import map_to_canonical
from app.domain.source_event import EmployeeCreatedEvent
from app.domain.statuses import RunStatus, StepName, StepStatus
from app.logging_config import correlation_id_var, get_logger
from app.orchestration.retry import RetryPolicy
from app.persistence.models import IntegrationRun, IntegrationStep, utcnow
from app.persistence.repository import DuplicateEventError, IntegrationRunRepository

logger = get_logger(__name__)

EMPLOYEE_CREATED_STEPS = [
    StepName.MAP_TO_CANONICAL,
    StepName.PROVISION_IDENTITY,
    StepName.CREATE_ONBOARDING_TASK,
    StepName.SEND_WELCOME_NOTIFICATION,
]


@dataclass
class OrchestrationOutcome:
    run: IntegrationRun
    duplicate: bool


class StepFailedError(Exception):
    def __init__(self, error: IntegrationError) -> None:
        super().__init__(error.safe_message)
        self.error = error


class EmployeeCreatedOrchestrator:
    def __init__(
        self,
        repository: IntegrationRunRepository,
        identity: IdentityConnector,
        collaboration: CollaborationConnector,
        notification: NotificationConnector,
        retry_policy: RetryPolicy,
    ) -> None:
        self.repo = repository
        self.identity = identity
        self.collaboration = collaboration
        self.notification = notification
        self.retry_policy = retry_policy

    def process(self, event: EmployeeCreatedEvent, correlation_id: str) -> OrchestrationOutcome:
        correlation_id_var.set(correlation_id)
        try:
            run = self.repo.create_run(
                source_event_id=event.event_id,
                event_type=event.event_type,
                correlation_id=correlation_id,
                steps=EMPLOYEE_CREATED_STEPS,
            )
        except DuplicateEventError as dup:
            logger.info(
                "Duplicate event received; returning existing integration run",
                extra={"event_id": event.event_id, "integration_run_id": dup.existing.id},
            )
            return OrchestrationOutcome(run=dup.existing, duplicate=True)

        log_ctx = {"event_id": event.event_id, "integration_run_id": run.id}
        logger.info("Integration run created", extra=log_ctx)
        # Schema validation happens at the API boundary before the run is created.
        self.repo.set_run_status(run, RunStatus.VALIDATED, note="Schema validation passed")
        self.repo.set_run_status(run, RunStatus.IN_PROGRESS)

        steps = {step.step_name: step for step in run.steps}
        try:
            employee: CanonicalEmployee = self._execute(
                run, steps[StepName.MAP_TO_CANONICAL], lambda: map_to_canonical(event.employee)
            )
            self._execute(
                run,
                steps[StepName.PROVISION_IDENTITY],
                lambda: self.identity.upsert_user(employee, correlation_id),
            )
            self._execute(
                run,
                steps[StepName.CREATE_ONBOARDING_TASK],
                lambda: self.collaboration.create_onboarding_task(
                    employee, f"{event.event_id}:{StepName.CREATE_ONBOARDING_TASK}", correlation_id
                ),
            )
            self._execute(
                run,
                steps[StepName.SEND_WELCOME_NOTIFICATION],
                lambda: self.notification.send_welcome(
                    employee,
                    f"{event.event_id}:{StepName.SEND_WELCOME_NOTIFICATION}",
                    correlation_id,
                ),
            )
        except StepFailedError as failure:
            self._finish_failed(run, failure.error)
            logger.warning(
                "Integration run did not complete",
                extra={
                    **log_ctx,
                    "status": run.status,
                    "error_category": failure.error.category,
                },
            )
            return OrchestrationOutcome(run=run, duplicate=False)

        self.repo.set_run_status(run, RunStatus.SUCCEEDED)
        logger.info("Integration run succeeded", extra={**log_ctx, "retry_count": run.retry_count})
        return OrchestrationOutcome(run=run, duplicate=False)

    def _execute[T](self, run: IntegrationRun, step: IntegrationStep, action: Callable[[], T]) -> T:
        step.status = StepStatus.IN_PROGRESS
        step.started_at = utcnow()
        self.repo.save()

        while True:
            step.attempts += 1
            try:
                result = action()
            except Exception as exc:
                error = classify_exception(exc, step.step_name)
                step.error_category = error.category
                step.error_message = error.safe_message
                retries_used = step.attempts - 1
                if error.retryable and retries_used < self.retry_policy.max_retries:
                    delay = self.retry_policy.delay_for_retry(retries_used + 1)
                    step.status = StepStatus.RETRYING
                    run.retry_count += 1
                    self.repo.set_run_status(
                        run,
                        RunStatus.RETRYING,
                        note=f"{step.step_name} attempt {step.attempts} failed "
                        f"({error.category}); retrying in {delay:.2f}s",
                    )
                    logger.info(
                        "Retrying step after transient error",
                        extra={
                            "integration_run_id": run.id,
                            "step": step.step_name,
                            "attempt": step.attempts,
                            "error_category": error.category,
                            "delay_seconds": delay,
                        },
                    )
                    self.retry_policy.sleep(delay)
                    continue
                step.status = StepStatus.FAILED
                step.finished_at = utcnow()
                self.repo.save()
                raise StepFailedError(error) from exc

            step.status = StepStatus.SUCCEEDED
            step.finished_at = utcnow()
            if isinstance(result, ConnectorResult):
                step.external_reference = result.external_reference
            if run.status == RunStatus.RETRYING:
                self.repo.set_run_status(
                    run, RunStatus.IN_PROGRESS, note=f"{step.step_name} succeeded after retry"
                )
            else:
                self.repo.save()
            return result

    def _finish_failed(self, run: IntegrationRun, error: IntegrationError) -> None:
        for step in run.steps:
            if step.status == StepStatus.PENDING:
                step.status = StepStatus.SKIPPED
        if error.category in SOURCE_CORRECTION_CATEGORIES:
            final, note = RunStatus.FAILED, "Non-retryable error; correct the source data"
        elif error.retryable:
            final, note = RunStatus.MANUAL_REVIEW_REQUIRED, "Retry limit exhausted"
        else:
            final, note = RunStatus.MANUAL_REVIEW_REQUIRED, "Non-retryable technical error"
        self.repo.set_run_status(
            run, final, note=note, error_category=error.category, error_message=error.safe_message
        )


__all__ = ["EmployeeCreatedOrchestrator", "OrchestrationOutcome"]
