"""Repository encapsulating integration run persistence."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.domain.statuses import RunStatus, StepName, StepStatus
from app.persistence.models import IntegrationRun, IntegrationStep, RunStatusHistory, utcnow


class DuplicateEventError(Exception):
    def __init__(self, existing: IntegrationRun) -> None:
        super().__init__("Duplicate source event")
        self.existing = existing


class IntegrationRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create_run(
        self, *, source_event_id: str, event_type: str, correlation_id: str, steps: list[StepName]
    ) -> IntegrationRun:
        """Create a run. Raises DuplicateEventError if the event was already received.

        The unique constraint on source_event_id is the authoritative idempotency guard,
        which also protects against concurrent submissions of the same event.
        """
        existing = self.get_by_event_id(source_event_id)
        if existing is not None:
            raise DuplicateEventError(existing)
        run = IntegrationRun(
            source_event_id=source_event_id,
            event_type=event_type,
            correlation_id=correlation_id,
            status=RunStatus.RECEIVED,
        )
        run.history.append(RunStatusHistory(status=RunStatus.RECEIVED))
        for index, name in enumerate(steps, start=1):
            run.steps.append(
                IntegrationStep(sequence=index, step_name=name, status=StepStatus.PENDING)
            )
        self.session.add(run)
        try:
            self.session.commit()
        except IntegrityError:
            self.session.rollback()
            existing = self.get_by_event_id(source_event_id)
            if existing is None:
                raise
            raise DuplicateEventError(existing) from None
        return run

    def set_run_status(
        self,
        run: IntegrationRun,
        status: RunStatus,
        *,
        note: str | None = None,
        error_category: str | None = None,
        error_message: str | None = None,
    ) -> None:
        run.status = status
        if status == RunStatus.IN_PROGRESS and run.started_at is None:
            run.started_at = utcnow()
        if status in (RunStatus.SUCCEEDED, RunStatus.FAILED, RunStatus.MANUAL_REVIEW_REQUIRED):
            run.finished_at = utcnow()
        if error_category:
            run.error_category = error_category
            run.error_message = error_message
        run.history.append(RunStatusHistory(status=status, note=note))
        self.session.commit()

    def save(self) -> None:
        self.session.commit()

    def get(self, run_id: str) -> IntegrationRun | None:
        stmt = (
            select(IntegrationRun)
            .where(IntegrationRun.id == run_id)
            .options(selectinload(IntegrationRun.steps), selectinload(IntegrationRun.history))
        )
        return self.session.scalars(stmt).first()

    def get_by_event_id(self, source_event_id: str) -> IntegrationRun | None:
        stmt = select(IntegrationRun).where(IntegrationRun.source_event_id == source_event_id)
        return self.session.scalars(stmt).first()

    def list_runs(self, status: str | None = None, limit: int = 50) -> list[IntegrationRun]:
        stmt = (
            select(IntegrationRun)
            .options(selectinload(IntegrationRun.steps))
            .order_by(IntegrationRun.received_at.desc())
            .limit(limit)
        )
        if status:
            stmt = stmt.where(IntegrationRun.status == status)
        return list(self.session.scalars(stmt))
