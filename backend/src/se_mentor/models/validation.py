from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from se_mentor.contracts.enums import EventType, FeedbackKind, FeedbackSeverity
from se_mentor.db.base import Base
from se_mentor.models.approval import ExecutionPolicy
from se_mentor.models.task import ChangeProposal, ChangeTask


class ValidationPlanStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUPERSEDED = "SUPERSEDED"
    EXPIRED = "EXPIRED"


class ValidationType(StrEnum):
    TEST = "TEST"
    LINT = "LINT"
    TYPE_CHECK = "TYPE_CHECK"
    MIGRATION = "MIGRATION"
    MANUAL = "MANUAL"


class ValidationRunStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    ERROR = "ERROR"
    SKIPPED = "SKIPPED"
    INCONCLUSIVE = "INCONCLUSIVE"


def _new_id() -> str:
    return str(uuid4())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _in_values(values: type[StrEnum]) -> str:
    quoted_values = ", ".join(f"'{item.value}'" for item in values)
    return f"({quoted_values})"


class ValidationPlan(Base):
    __tablename__ = "validation_plans"
    __table_args__ = (
        CheckConstraint("version >= 1", name="version_positive"),
        CheckConstraint(f"status IN {_in_values(ValidationPlanStatus)}", name="status_values"),
        CheckConstraint("length(trim(required_checks_json)) > 0", name="required_checks_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index(
            "ix_validation_plans_proposal_policy_version",
            "proposal_id",
            "execution_policy_id",
            "version",
            unique=True,
        ),
        Index("ix_validation_plans_task_id_status", "task_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    proposal_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("change_proposals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    execution_policy_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("execution_policies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    required_checks_json: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    task: Mapped[ChangeTask] = relationship()
    proposal: Mapped[ChangeProposal] = relationship()
    execution_policy: Mapped[ExecutionPolicy] = relationship()
    runs: Mapped[list[ValidationRun]] = relationship(
        "ValidationRun", back_populates="validation_plan"
    )


class ValidationRun(Base):
    __tablename__ = "validation_runs"
    __table_args__ = (
        CheckConstraint("run_order >= 1", name="run_order_positive"),
        CheckConstraint(
            f"validation_type IN {_in_values(ValidationType)}", name="validation_type_values"
        ),
        CheckConstraint(f"status IN {_in_values(ValidationRunStatus)}", name="status_values"),
        CheckConstraint("exit_code IS NULL OR exit_code >= 0", name="exit_code_non_negative"),
        CheckConstraint("length(trim(command_summary)) > 0", name="command_summary_non_empty"),
        CheckConstraint("length(trim(log_artifact_ref)) > 0", name="log_artifact_ref_non_empty"),
        CheckConstraint(
            "status != 'PASSED' OR (exit_code = 0 AND required_failure = 0)",
            name="passed_requires_zero_exit_no_required_failure",
        ),
        Index(
            "ix_validation_runs_plan_order",
            "validation_plan_id",
            "run_order",
            unique=True,
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    validation_plan_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("validation_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    run_order: Mapped[int] = mapped_column(nullable=False)
    validation_type: Mapped[str] = mapped_column(String(16), nullable=False)
    command_summary: Mapped[str] = mapped_column(String(2048), nullable=False)
    exit_code: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    required: Mapped[bool] = mapped_column(Boolean, nullable=False)
    required_failure: Mapped[bool] = mapped_column(Boolean, nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    log_artifact_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )

    validation_plan: Mapped[ValidationPlan] = relationship(back_populates="runs")


class FeedbackSignal(Base):
    __tablename__ = "feedback_signals"
    __table_args__ = (
        CheckConstraint(f"kind IN {_in_values(FeedbackKind)}", name="kind_values"),
        CheckConstraint(f"severity IN {_in_values(FeedbackSeverity)}", name="severity_values"),
        CheckConstraint("length(trim(summary)) > 0", name="summary_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_feedback_signals_task_id_kind", "task_id", "kind"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    summary: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )


class ProgressEvent(Base):
    __tablename__ = "progress_events"
    __table_args__ = (
        CheckConstraint(f"event_type IN {_in_values(EventType)}", name="event_type_values"),
        CheckConstraint("length(trim(summary)) > 0", name="summary_non_empty"),
        CheckConstraint("length(trim(evidence_json)) > 0", name="evidence_non_empty"),
        Index("ix_progress_events_task_id_event_type", "task_id", "event_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_new_id)
    task_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("change_tasks.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(String(2048), nullable=False)
    evidence_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, nullable=False
    )
