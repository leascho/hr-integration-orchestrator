"""Audit persistence model. Deliberately stores no employee PII."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class IntegrationRun(Base):
    __tablename__ = "integration_runs"
    __table_args__ = (UniqueConstraint("source_event_id", name="uq_runs_source_event_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    correlation_id: Mapped[str] = mapped_column(String(64), index=True)
    source_event_id: Mapped[str] = mapped_column(String(64))
    event_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), index=True)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    steps: Mapped[list["IntegrationStep"]] = relationship(
        back_populates="run", order_by="IntegrationStep.sequence", cascade="all, delete-orphan"
    )
    history: Mapped[list["RunStatusHistory"]] = relationship(
        back_populates="run", order_by="RunStatusHistory.id", cascade="all, delete-orphan"
    )


class IntegrationStep(Base):
    __tablename__ = "integration_steps"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("integration_runs.id"), index=True)
    sequence: Mapped[int] = mapped_column(Integer)
    step_name: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    error_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    external_reference: Mapped[str | None] = mapped_column(String(128), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    run: Mapped[IntegrationRun] = relationship(back_populates="steps")


class RunStatusHistory(Base):
    __tablename__ = "integration_run_status_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("integration_runs.id"), index=True)
    status: Mapped[str] = mapped_column(String(32))
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    run: Mapped[IntegrationRun] = relationship(back_populates="history")
